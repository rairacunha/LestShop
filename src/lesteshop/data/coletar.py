"""Coleta sob demanda no Compras Paraguai e grava na base.

Exemplos::

    python -m lesteshop.data.coletar "playstation 5 pro"
    python -m lesteshop.data.coletar "playstation 5 pro" --listar          # só mostra os modelos achados
    python -m lesteshop.data.coletar --url https://www.comprasparaguai.com.br/<slug>_<id>/
    python -m lesteshop.data.coletar "iphone 16" --max-modelos 3 --categoria Celulares
    python -m lesteshop.data.coletar "playstation 5 pro" --navegador   # janela do Chromium; você resolve a verificação
    python -m lesteshop.data.coletar --arquivo data/coleta_exemplo.json --navegador --max-modelos 2
    python -m lesteshop.data.coletar --url-categoria https://www.comprasparaguai.com.br/celular/ \
        --categoria Celulares --paginas 2 --navegador

Com ``--url-categoria`` (vitrine de uma categoria do site), o coletor lê os cards de modelo
das ``--paginas`` primeiras páginas (padrão 2; só o parâmetro ``page`` da URL muda) com o
mesmo leitor da busca e coleta cada modelo pelo mesmo caminho da busca por termo (mesma
limpeza e mesma gravação). Exige ``--categoria``, que é gravada nos produtos.

Com ``--arquivo`` (JSON com uma lista de {"termo", "categoria"}), cada termo é coletado com
a sua categoria; se um termo der erro, a coleta segue com os outros e o resumo no fim
mostra o que deu certo e o que falhou. Entre um acesso e outro ao site, o coletor espera
10 s fixos e respeita o robots.txt (sem pausas aleatórias para disfarçar o acesso).

Cada coleta é salva em data/coletas/<AAAA-MM-DD>/ (CSV, versionável) e gravada
no SQLite (data/lesteshop.db).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
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


def carregar_fila(termos: list[str], categoria: str | None, arquivo: str | None) -> list[dict]:
    """Lista de {"termo", "categoria"}: primeiro a do arquivo JSON, depois os termos avulsos
    (com a ``--categoria``). Termos repetidos entram uma vez só."""
    fila: list[dict] = []
    if arquivo:
        dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
        if not isinstance(dados, list):
            raise ValueError(f"{arquivo}: o JSON deve ser uma lista de objetos {{\"termo\", \"categoria\"}}.")
        for i, item in enumerate(dados, start=1):
            termo = (item.get("termo") or "").strip() if isinstance(item, dict) else ""
            if not termo:
                raise ValueError(f"{arquivo}: o item {i} não tem \"termo\".")
            fila.append({"termo": termo, "categoria": (item.get("categoria") or categoria or None)})
    fila += [{"termo": t.strip(), "categoria": categoria} for t in termos if t.strip()]
    vistos, unicos = set(), []
    for item in fila:
        if item["termo"].lower() not in vistos:
            vistos.add(item["termo"].lower())
            unicos.append(item)
    return unicos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coleta ofertas reais no Compras Paraguai (Ciudad del Este).")
    parser.add_argument("termos", nargs="*", help="o que buscar, ex.: \"playstation 5 pro\"")
    parser.add_argument("--url", action="append", default=[], help="URL de uma página de modelo (pode repetir)")
    parser.add_argument("--max-modelos", type=int, default=None,
                        help="quantos modelos coletar por termo (padrão 1) ou por categoria (padrão: todos das páginas)")
    parser.add_argument("--url-categoria", action="append", default=[],
                        help="URL da vitrine de uma categoria do Compras Paraguai (pode repetir; exige --categoria)")
    parser.add_argument("--paginas", type=int, default=2,
                        help="quantas páginas ler de cada --url-categoria (padrão 2)")
    parser.add_argument("--categoria", help="categoria a gravar nos produtos coletados (termos avulsos)")
    parser.add_argument("--arquivo", help="JSON com uma lista de {\"termo\", \"categoria\"}")
    parser.add_argument("--listar", action="store_true", help="só lista os modelos encontrados na busca")
    parser.add_argument("--banco", default=str(config.CAMINHO_BANCO))
    parser.add_argument("--navegador", action="store_true",
                        help="baixa pelo Chromium visível; você resolve a verificação anti-robô do site")
    args = parser.parse_args(argv)
    try:
        args.fila = carregar_fila(args.termos, args.categoria, args.arquivo)
    except (OSError, ValueError) as e:
        parser.error(str(e))
    if not args.fila and not args.url and not args.url_categoria:
        parser.error("informe ao menos um termo de busca, --arquivo, --url ou --url-categoria")
    if args.url_categoria and not args.categoria:
        parser.error("--url-categoria exige --categoria (a categoria gravada nos produtos)")
    if args.paginas < 1:
        parser.error("--paginas deve ser pelo menos 1")

    cliente = ClienteNavegador() if args.navegador else None
    try:
        return _coletar(args, cliente)
    finally:
        if cliente is not None:
            cliente.fechar()


def _coletar(args, cliente) -> int:
    """Coleta cada item da fila (e as --url) separadamente: um erro não perde os outros."""
    if args.listar:
        fonte = FonteComprasParaguai(cliente=cliente)
        try:
            for termo in [i["termo"] for i in args.fila]:
                print(f"Modelos para '{termo}':")
                for m in fonte.buscar_modelos(termo):
                    preco = f"US$ {m['preco_a_partir_usd']:.2f}" if m["preco_a_partir_usd"] else "sem preço"
                    print(f"  {m['nome']}  (a partir de {preco})  {m['url']}")
        except (ErroColeta, ErroEstruturaHTML) as e:
            print(f"ERRO na busca: {e}")
            return 1
        return 0

    tarefas = [{"termos": [i["termo"]], "urls": [], "categoria": i["categoria"], "rotulo": f"'{i['termo']}'"}
               for i in args.fila]
    tarefas += [{"termos": [], "urls": None, "url_categoria": u, "categoria": args.categoria,
                 "rotulo": f"categoria {u}"} for u in args.url_categoria]
    if args.url:
        tarefas.append({"termos": [], "urls": args.url, "categoria": args.categoria,
                        "rotulo": f"{len(args.url)} URL(s) de modelo"})
    resumo: list[tuple[str, str]] = []
    for n, t in enumerate(tarefas, start=1):
        if len(tarefas) > 1:
            print(f"[{t['categoria'] or 'sem categoria'}] ({n}/{len(tarefas)}) Coletando {t['rotulo']}…")
        if t.get("url_categoria"):
            try:
                modelos = FonteComprasParaguai(cliente=cliente).modelos_da_categoria(
                    t["url_categoria"], args.paginas)
            except (ErroColeta, ErroEstruturaHTML) as e:
                print(f"ERRO ao ler a vitrine da categoria: {e}")
                resumo.append((t["rotulo"], f"FALHOU: {e}"))
                continue
            if args.max_modelos:
                modelos = modelos[: args.max_modelos]
            print(f"  {len(modelos)} modelo(s) na vitrine ({args.paginas} página(s) no máximo).")
            if not modelos:
                resumo.append((t["rotulo"], "FALHOU: nenhum modelo na vitrine"))
                continue
            t["urls"] = [m["url"] for m in modelos]
        fonte = FonteComprasParaguai(termos=t["termos"], urls_modelos=t["urls"], cliente=cliente,
                                     max_modelos_por_termo=args.max_modelos or 1, categoria=t["categoria"])
        ok, texto = _coletar_um(args, fonte)
        resumo.append((t["rotulo"], ("OK: " if ok else "FALHOU: ") + texto))
    if len(tarefas) > 1:
        print("\nResumo da coleta:")
        for rotulo, texto in resumo:
            print(f"  {rotulo}: {texto}")
    return 0 if all(t.startswith("OK") for _, t in resumo) else 1


def _coletar_um(args, fonte) -> tuple[bool, str]:
    try:
        res = fonte.coletar()
    except (ErroColeta, ErroEstruturaHTML) as e:
        print(f"ERRO na coleta: {e}")
        print("Nada foi gravado.")
        return False, str(e)

    if res.ofertas.empty:
        print("Nenhuma oferta de Ciudad del Este encontrada; nada foi gravado.")
        return False, "nenhuma oferta em Ciudad del Este"
    val = validar(res.lojas, res.produtos, res.ofertas)
    if not val.ok:
        print("ERRO: os dados coletados não passaram na validação; nada foi gravado.")
        for e in val.erros:
            print(f"  - {e}")
        return False, "dados não passaram na validação"

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
    return True, f"{len(val.produtos)} produto(s), {len(val.ofertas)} oferta(s)"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
