"""Matriz de tempos de deslocamento a pé entre a Ponte da Amizade (nó 0) e as lojas.

t_ij = haversine(i, j) × fator de circuidade ÷ velocidade a pé, em minutos.
Lojas do mesmo prédio (exceto "Rua (loja de rua)") levam um tempo fixo
(``TEMPO_MESMO_PREDIO_MIN``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from . import config
from ..data.texto import normalizar

RAIO_TERRA_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância geodésica (grande círculo) em metros."""
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df = f2 - f1
    dl = math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_M * math.asin(min(1.0, math.sqrt(a)))


def agrupa_predio(predio: str | None) -> bool:
    """True se o prédio identifica um edifício (lojas nele ficam a ~0 de distância)."""
    if predio is None or (isinstance(predio, float) and math.isnan(predio)):
        return False
    texto = normalizar(str(predio))
    if not texto:
        return False
    return texto.split()[0] not in config.PREDIOS_SEM_AGRUPAMENTO


def mesmo_predio(p1: str | None, p2: str | None) -> bool:
    return agrupa_predio(p1) and agrupa_predio(p2) and normalizar(str(p1)) == normalizar(str(p2))


def matriz_tempos(
    coordenadas: Sequence[tuple[float, float]],
    predios: Sequence[str | None],
    velocidade_m_por_min: float = config.VELOCIDADE_M_POR_MIN,
    fator_circuidade: float = config.FATOR_CIRCUIDADE,
    tempo_mesmo_predio: float = config.TEMPO_MESMO_PREDIO_MIN,
) -> np.ndarray:
    """Matriz n × n de minutos (diagonal 0). Posição 0 = nó 0 (Ponte), com prédio None."""
    n = len(coordenadas)
    if len(predios) != n:
        raise ValueError("coordenadas e predios devem ter o mesmo tamanho.")
    t = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            if mesmo_predio(predios[i], predios[j]):
                v = tempo_mesmo_predio
            else:
                d = haversine_m(*coordenadas[i], *coordenadas[j])
                v = d * fator_circuidade / velocidade_m_por_min
                v = max(v, tempo_mesmo_predio)  # nenhum deslocamento entre nós distintos é 0
            t[i, j] = t[j, i] = v
    return t
