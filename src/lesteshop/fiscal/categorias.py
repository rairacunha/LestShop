"""Correspondência produto → categoria fiscal (``data/categorias_fiscais.csv``).

Arquivo editável à mão. Cada linha liga uma ``categoria`` de ``produtos.categoria``
a uma ``categoria_fiscal`` das regras. Uma linha com ``produto_id`` vale só para
aquele produto e tem precedência sobre a linha da categoria; é nela que se informa
o ``conteudo_por_unidade`` (litros de bebida por garrafa, maços por pacote, gramas
de fumo), porque a coluna ``produtos.volume_l`` é o volume da embalagem.

Produto cuja categoria não aparece no arquivo é tratado como ``outros`` (entra nos
limites de unidades), com aviso.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..data import config as config_dados

CAMINHO_CATEGORIAS = config_dados.DIR_DADOS / "categorias_fiscais.csv"
CATEGORIA_PADRAO = "outros"
COLUNAS = ["categoria", "produto_id", "categoria_fiscal", "conteudo_por_unidade", "observacao"]


@dataclass(frozen=True)
class Classificacao:
    categoria_fiscal: str
    conteudo_por_unidade: float | None   # None = não informado
    aviso: str = ""


class MapaCategorias:
    def __init__(self, por_categoria: dict[str, Classificacao], por_produto: dict[str, Classificacao]):
        self.por_categoria = por_categoria
        self.por_produto = por_produto

    def classificar(self, produto_id: str, categoria: str | None) -> Classificacao:
        if produto_id in self.por_produto:
            return self.por_produto[produto_id]
        cat = (categoria or "").strip()
        if cat in self.por_categoria:
            return self.por_categoria[cat]
        return Classificacao(
            CATEGORIA_PADRAO, None,
            f"categoria '{cat or '(vazia)'}' do produto {produto_id} não está em "
            f"categorias_fiscais.csv: tratado como '{CATEGORIA_PADRAO}'.",
        )


def _conteudo(v) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    f = float(v)
    return None if math.isnan(f) else f


def carregar_categorias(caminho: str | Path = CAMINHO_CATEGORIAS) -> MapaCategorias:
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    faltando = [c for c in COLUNAS[:4] if c not in df.columns]
    if faltando:
        raise ValueError(f"{caminho}: faltam as colunas {', '.join(faltando)}.")
    por_cat: dict[str, Classificacao] = {}
    por_prod: dict[str, Classificacao] = {}
    for row in df.to_dict("records"):
        c = Classificacao(row["categoria_fiscal"].strip(), _conteudo(row["conteudo_por_unidade"]))
        if not c.categoria_fiscal:
            raise ValueError(f"{caminho}: linha sem categoria_fiscal ({row}).")
        pid = row["produto_id"].strip()
        if pid:
            por_prod[pid] = c
        else:
            por_cat[row["categoria"].strip()] = c
    return MapaCategorias(por_cat, por_prod)
