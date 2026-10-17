"""Coleta sob demanda no Compras Paraguai e grava na base.

Exemplos::

    python -m lesteshop.data.coletar "playstation 5 pro"
    python -m lesteshop.data.coletar "playstation 5 pro" --listar          # só mostra os modelos achados
    python -m lesteshop.data.coletar --url https://www.comprasparaguai.com.br/<slug>_<id>/
    python -m lesteshop.data.coletar "iphone 16" --max-modelos 3 --categoria Celulares
    python -m lesteshop.data.coletar "playstation 5 pro" --navegador   # janela do Chromium; você resolve a verificação

Cada coleta é salva em data/coletas/<AAAA-MM-DD>/ (CSV, versionável) e gravada
no SQLite (data/lesteshop.db).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

import pandas as pd

from . import config, database, esquema
from .sources.comprasparaguai import FonteComprasParaguai, ResultadoColeta
from .sources.http import ErroColeta
from .sources.navegador import ClienteNavegador
from .sources.parser_cp import ErroEstruturaHTML
from .validator import validar

log = logging.getLogger(__name__)


def salvar_coleta_csv(res: ResultadoColeta, pasta: Path) -> None:
    """Acrescenta a coleta aos CSVs do dia (sem duplicar)."""
    pasta.mkdir(parents=True, exist_ok=True)
    chaves = {"lojas": ["loja_id"], "produtos": ["produto_id"],
              "ofertas": ["loja_id", "produto_id", "codigo_loja", "titulo_oferta", "data_coleta"],
              "descartes": None}
    for nome, df in (("lojas", res.lojas), ("produtos", res.produtos),
                     ("ofertas", res.ofertas), ("descartes", res.descartes)):
        arq = pasta / f"{nome}.csv"
        if arq.exists():
            antigo = pd.read_csv(arq, dtype=str, keep_default_na=False, na_values=[""])
            df = pd.concat([antigo, df.astype(object)], ignore_index=True)
        df = df.drop_duplicates(subset=chaves[nome], keep="last") if chaves[nome] else df.drop_duplicates()
        if nome != "descartes":
            df = esquema.padronizar(df, nome)
        df.to_csv(arq, index=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coleta ofertas reais no Compras Paraguai (Ciudad del Este).")
    parser.add_argument("termos", nargs="*", help="o que buscar, ex.: \"playstation 5 pro\"")
    parser.add_argument("--url", action="append", default=[], help="URL de uma página de modelo (pode repetir)")
    parser.add_argument("--max-modelos", type=int, default=1, help="quantos modelos coletar por termo (padrão 1)")
    parser.add_argument("--categoria", help="categoria a gravar nos produtos coletados")
    parser.add_argument("--listar", action="store_true", help="só lista os modelos encontrados na busca")
    parser.add_argument("--banco", default=str(config.CAMINHO_BANCO))
    parser.add_argument("--navegador", action="store_true",
                        help="baixa pelo Chromium visível; você resolve a verificação anti-robô do site")
    args = parser.parse_args(argv)
    if not args.termos and not args.url:
        parser.error("informe ao menos um termo de busca ou --url")

    cliente = ClienteNavegador() if args.navegador else None
    try:
        return _coletar(args, cliente)
    finally:
        if cliente is not None:
            cliente.fechar()


def _coletar(args, cliente) -> int:
    fonte = FonteComprasParaguai(termos=args.termos, urls_modelos=args.url, cliente=cliente,
                                 max_modelos_por_termo=args.max_modelos, categoria=args.categoria)
    try:
        if args.listar:
            for termo in args.termos:
                print(f"Modelos para '{termo}':")
                for m in fonte.buscar_modelos(termo):
                    preco = f"US$ {m['preco_a_partir_usd']:.2f}" if m["preco_a_partir_usd"] else "sem preço"
                    print(f"  {m['nome']}  (a partir de {preco})  {m['url']}")
            return 0
        res = fonte.coletar()
    except (ErroColeta, ErroEstruturaHTML) as e:
        print(f"ERRO na coleta: {e}")
        print("Nada foi gravado.")
        return 1

    if res.ofertas.empty:
        print("Nenhuma oferta de Ciudad del Este encontrada; nada foi gravado.")
        return 1
    val = validar(res.lojas, res.produtos, res.ofertas)
    if not val.ok:
        print("ERRO: os dados coletados não passaram na validação; nada foi gravado.")
        for e in val.erros:
            print(f"  - {e}")
        return 1

    hoje = dt.date.today().isoformat()
    salvar_coleta_csv(res, config.DIR_COLETAS / hoje)
    con = database.conectar(args.banco)
    if con.execute("SELECT COUNT(*) FROM pontos_partida").fetchone()[0] == 0:
        database.gravar_tabela_simples(con, "pontos_partida",
                                       database.FonteCSV(config.DIR_RAW).carregar_pontos_partida())
    lojas = database.aplicar_complemento_lojas(val.lojas)
    database.gravar(con, lojas, val.produtos, val.ofertas, res.descartes)
    con.close()

    print(f"Coleta de {hoje} gravada em {args.banco} e em {config.DIR_COLETAS / hoje}:")
    print(f"  {len(val.produtos)} produto(s), {len(val.lojas)} loja(s), {len(val.ofertas)} oferta(s) em Ciudad del Este")
    print(f"  {len(res.descartes)} oferta(s) descartada(s) por cidade: {res.descartadas_por_cidade or '-'}")
    pendentes = lojas[lojas["coordenada_pendente"]]
    if len(pendentes):
        print(f"  {len(pendentes)} loja(s) com coordenada pendente (preencha em data/lojas_complemento.csv):")
        for r in pendentes.itertuples():
            print(f"    - {r.loja_id}: {r.nome} | {r.endereco or 'sem endereço'}")
    for a in val.alertas + res.avisos:
        print(f"  ALERTA: {a}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
