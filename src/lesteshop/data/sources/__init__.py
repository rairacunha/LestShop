"""Fontes de dados de ofertas (padrão adapter).

O restante do código depende apenas de :class:`FonteDeOfertas`.
"""

from .base import FonteDeOfertas
from .fonte_api import FonteAPI
from .fonte_csv import FonteCSV
from .comprasparaguai import FonteComprasParaguai

__all__ = ["FonteDeOfertas", "FonteCSV", "FonteComprasParaguai", "FonteAPI"]
