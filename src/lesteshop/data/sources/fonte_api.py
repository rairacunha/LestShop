"""Esqueleto de fonte baseada em API oficial de preços."""

from __future__ import annotations

import pandas as pd

from .base import FonteDeOfertas


class FonteAPI(FonteDeOfertas):
    """Fonte reservada para uma API oficial de preços.

    Será implementada se conseguirmos acesso a uma API oficial (das lojas ou
    de um agregador). Basta devolver DataFrames no formato de
    ``esquema.COLUNAS`` para que o resto do sistema funcione sem mudanças.
    """

    nome = "api"

    def __init__(self, url_base: str | None = None, chave: str | None = None):
        self.url_base = url_base
        self.chave = chave

    def carregar_lojas(self) -> pd.DataFrame:
        raise NotImplementedError("FonteAPI ainda não implementada: não temos acesso a uma API oficial de preços.")

    def carregar_produtos(self) -> pd.DataFrame:
        raise NotImplementedError("FonteAPI ainda não implementada: não temos acesso a uma API oficial de preços.")

    def carregar_ofertas(self) -> pd.DataFrame:
        raise NotImplementedError("FonteAPI ainda não implementada: não temos acesso a uma API oficial de preços.")
