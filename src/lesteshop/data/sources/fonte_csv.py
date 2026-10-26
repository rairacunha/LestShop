"""Fonte que lê lojas.csv, produtos.csv e ofertas.csv de uma pasta."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .. import config, esquema
from .base import FonteDeOfertas


class FonteCSV(FonteDeOfertas):
    """Lê os CSVs de uma pasta (padrão: ``data/raw``, a base-semente).

    Usada como fallback quando não há internet, nos testes e para recriar o
    banco a partir das coletas salvas em ``data/coletas/<data>/``.
    """

    nome = "csv"

    def __init__(self, pasta: str | Path = config.DIR_RAW):
        self.pasta = Path(pasta)

    def _ler(self, tabela: str) -> pd.DataFrame:
        caminho = self.pasta / f"{tabela}.csv"
        if not caminho.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
        df = pd.read_csv(caminho, dtype=str, keep_default_na=False, na_values=[""])
        return esquema.padronizar(df, tabela)

    def carregar_lojas(self) -> pd.DataFrame:
        return self._ler("lojas")

    def carregar_produtos(self) -> pd.DataFrame:
        return self._ler("produtos")

    def carregar_ofertas(self) -> pd.DataFrame:
        return self._ler("ofertas")

    def carregar_cotacoes(self) -> pd.DataFrame:
        caminho = self.pasta / "cotacoes.csv"
        if not caminho.exists():
            return esquema.vazio("cotacoes")
        return esquema.padronizar(pd.read_csv(caminho, dtype={"data": str}), "cotacoes")

    def carregar_pontos_partida(self) -> pd.DataFrame:
        caminho = self.pasta / "pontos_partida.csv"
        if not caminho.exists():
            return esquema.vazio("pontos_partida")
        return esquema.padronizar(pd.read_csv(caminho), "pontos_partida")
