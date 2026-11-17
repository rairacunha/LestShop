"""Fase 3 — regras fiscais e de bagagem.

* ``regras``: tabela versionada ``data/regras_fiscais.csv`` (cota e limites);
* ``categorias``: correspondência produto → categoria fiscal
  (``data/categorias_fiscais.csv``, editável à mão);
* ``verificacao``: compara a cesta escolhida com os limites e gera os alertas.

Os limites quantitativos são só alertas: o modelo de otimização da Fase 2 não muda.
Legislação e fontes: ``docs/legislacao_bagagem.md``.
"""

from .categorias import MapaCategorias, carregar_categorias
from .regras import Regra, RegrasFiscais, carregar_regras
from .verificacao import ItemCesta, verificar

__all__ = [
    "ItemCesta", "MapaCategorias", "Regra", "RegrasFiscais",
    "carregar_categorias", "carregar_regras", "verificar",
]
