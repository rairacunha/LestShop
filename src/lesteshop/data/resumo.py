"""Carrega e valida a base, imprime o resumo e exporta CSVs para revisão.

Uso::

    python -m lesteshop.data.resumo                 # usa data/lesteshop.db (recria a partir dos CSVs se não existir)
    python -m lesteshop.data.resumo --recriar       # recria o banco antes
    python -m lesteshop.data.resumo --sem-cotacao   # não consulta o Banco Central
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from . import config, database
from .cotacao import ErroCotacao, obter_cotacao, usd_para_brl
from .validator import validar


def montar_resumo(tabelas: dict[str, pd.DataFrame], cotacao=None, erro_cotacao: str | None = None) -> str:
    val = validar(tabelas["lojas"], tabelas["produtos"], tabelas["ofertas"])
    lojas, produtos, ofertas = val.lojas, val.produtos, val.ofertas
    linhas = ["=" * 72, "RESUMO DA BASE DE OFERTAS - LesteShop (Fase 1)", "=" * 72]
    tipos = ofertas["tipo_dado"].value_counts().to_dict()
    linhas.append(f"Lojas: {len(lojas)}   Produtos: {len(produtos)}   Ofertas: {len(ofertas)}   "
                  f"(ofertas por tipo_dado: {tipos})")
    if len(lojas) and len(produtos):
        linhas.append(f"Densidade da matriz loja x produto: {len(ofertas.drop_duplicates(['loja_id', 'produto_id'])) / (len(lojas) * len(produtos)):.1%}")
    if cotacao is not None:
        linhas.append(f"Cotação usada (só para exibir R$): {cotacao}")
    else:
        linhas.append(f"Cotação usada: indisponível ({str(erro_cotacao).rstrip(".")}); valores mostrados só em US$.")

    linhas += ["", "Preços por produto (US$):"]
    est = ofertas.groupby("produto_id")["preco_usd"].agg(menor="min", maior="max")
    est["lojas"] = ofertas.groupby("produto_id")["loja_id"].nunique()
    est = est.join(produtos.set_index("produto_id")["nome"]).sort_values("nome")
    largura = min(60, max([len(n) for n in est["nome"]] + [7]))
    linhas.append(f"  {'Produto':<{largura}}  {'Menor':>9}  {'Maior':>9}  Lojas" + ("  Menor (R$)" if cotacao else ""))
    for r in est.itertuples():
        brl = f"  {usd_para_brl(r.menor, cotacao):>10.2f}" if cotacao else ""
        linhas.append(f"  {r.nome[:largura]:<{largura}}  {r.menor:>9.2f}  {r.maior:>9.2f}  {r.lojas:>5}{brl}")

    pend = lojas[lojas["coordenada_pendente"]]
    linhas += ["", f"Lojas com coordenada pendente: {len(pend)}"]
    linhas += [f"  - {r.loja_id}: {r.nome} | {r.endereco or 'sem endereço'}" for r in pend.itertuples()]

    desc = tabelas.get("descartes_coleta")
    n_desc = 0 if desc is None else len(desc)
    linhas += ["", f"Ofertas descartadas por cidade (fora de Ciudad del Este): {n_desc}"]
    if n_desc:
        for cidade, n in desc["cidade"].fillna("não identificada").value_counts().items():
            linhas.append(f"  - {cidade}: {n}")

    if val.lojas_descartadas:
        linhas += ["", "Lojas descartadas por não terem ofertas:"] + [f"  - {l}" for l in val.lojas_descartadas]
    if val.alertas:
        linhas += ["", "Alertas:"] + [f"  - {a}" for a in val.alertas]
    linhas += ["", "Validação: " + ("OK" if val.ok else "FALHOU")]
    linhas += [f"  - {e}" for e in val.erros]
    return "\n".join(linhas)


def exportar(tabelas: dict[str, pd.DataFrame], pasta: Path = config.DIR_EXPORT) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in ("lojas", "produtos", "ofertas"):
        tabelas[nome].to_csv(pasta / f"{nome}.csv", index=False)
    return pasta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resumo e validação da base do LesteShop.")
    parser.add_argument("--banco", default=str(config.CAMINHO_BANCO))
    parser.add_argument("--recriar", action="store_true", help="recria o banco a partir dos CSVs antes")
    parser.add_argument("--incluir-semente", action="store_true")
    parser.add_argument("--sem-cotacao", action="store_true")
    parser.add_argument("--export", default=str(config.DIR_EXPORT))
    args = parser.parse_args(argv)

    if args.recriar or not Path(args.banco).exists():
        con = database.recriar_banco(args.banco, incluir_semente=args.incluir_semente)
    else:
        con = database.conectar(args.banco)
    tabelas = database.carregar_tabelas(con)
    cot, erro = None, "não consultada (--sem-cotacao)"
    if not args.sem_cotacao:
        try:
            cot = obter_cotacao(con=con)
        except ErroCotacao as e:
            erro = str(e)
    print(montar_resumo(tabelas, cot, erro))
    pasta = exportar(tabelas, Path(args.export))
    print(f"\nCSVs exportados para revisão em {pasta}/ (lojas.csv, produtos.csv, ofertas.csv).")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
