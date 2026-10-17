"""Constantes e caminhos usados em toda a Fase 1."""

from __future__ import annotations

import os
from pathlib import Path

# Raiz do projeto (pasta que contém data/, src/, tests/). Pode ser trocada
# pela variável de ambiente LESTESHOP_RAIZ (útil em testes).
RAIZ = Path(os.environ.get("LESTESHOP_RAIZ", Path(__file__).resolve().parents[3]))

DIR_DADOS = RAIZ / "data"
DIR_RAW = DIR_DADOS / "raw"
DIR_COLETAS = DIR_DADOS / "coletas"
DIR_INSTANCIAS = DIR_DADOS / "instances"
DIR_EXPORT = DIR_DADOS / "export"
DIR_CACHE = DIR_DADOS / "cache"
CAMINHO_BANCO = DIR_DADOS / "lesteshop.db"
CAMINHO_CATALOGO = DIR_DADOS / "catalogo_modelos.csv"
CAMINHO_META_CATALOGO = DIR_DADOS / "catalogo_meta.json"
CAMINHO_COMPLEMENTO_LOJAS = DIR_DADOS / "lojas_complemento.csv"

# --- Fonte Compras Paraguai -------------------------------------------------
URL_BASE_CP = "https://www.comprasparaguai.com.br"
FONTE_CP = "comprasparaguai.com.br"
INTERVALO_MIN_SEGUNDOS = 10.0
USER_AGENT = (
    "LesteShop/0.1 (projeto academico de Pesquisa Operacional II; "
    "coleta sob demanda, 1 requisicao a cada 10 s; "
    + os.environ.get("LESTESHOP_CONTATO", "sem contato configurado")
    + ")"
)

# --- Geografia --------------------------------------------------------------
CIDADE_ALVO = "Ciudad del Este"

# Retângulo que envolve a área urbana de Ciudad del Este (graus decimais).
# É propositalmente folgado; a borda leste (-54.597) fica a oeste do rio
# Paraná, para não aceitar coordenadas de Foz do Iguaçu.
CDE_LAT_MIN, CDE_LAT_MAX = -25.60, -25.42
CDE_LON_MIN, CDE_LON_MAX = -54.75, -54.597

# --- Valores permitidos -----------------------------------------------------
TIPOS_DADO = ("real", "estimado", "sintetico")
DIAS_VALIDADE_OFERTA = 30
