"""Interface comum a todas as fontes de ofertas."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class FonteDeOfertas(ABC):
    """Uma fonte entrega lojas, produtos e ofertas no formato de ``esquema.COLUNAS``.

    O resto do sistema (validação, banco, gerador) recebe uma ``FonteDeOfertas``
    e nunca precisa saber se os dados vieram de CSV, do Compras Paraguai ou de
    uma API.
    """

    #: Identificação da fonte gravada na coluna ``fonte``.
    nome: str = "desconhecida"

    @abstractmethod
    def carregar_lojas(self) -> pd.DataFrame:
        """Tabela ``lojas``."""

    @abstractmethod
    def carregar_produtos(self) -> pd.DataFrame:
        """Tabela ``produtos``."""

    @abstractmethod
    def carregar_ofertas(self) -> pd.DataFrame:
        """Tabela ``ofertas``."""

    def carregar_tudo(self) -> dict[str, pd.DataFrame]:
        return {
            "lojas": self.carregar_lojas(),
            "produtos": self.carregar_produtos(),
            "ofertas": self.carregar_ofertas(),
        }
