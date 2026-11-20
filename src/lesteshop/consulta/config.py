"""Parâmetros da consulta sob demanda."""

from __future__ import annotations

from ..data import config as config_dados

CAMINHO_CATALOGO_APP = config_dados.DIR_DADOS / "catalogo_app.json"
CAMINHO_CACHE = config_dados.DIR_CACHE / "consulta.db"

# Resultado de um item consultado vale por 6 horas; depois disso, nova consulta.
VALIDADE_CACHE_H = 6.0

# Intervalo mínimo entre requisições ao site durante a consulta do app (segundos).
# Se o robots.txt do site pedir um Crawl-delay maior, vale o do robots.txt.
INTERVALO_S = 1.5
