"""Parâmetros padrão da Fase 2 (todos os valores monetários em US$)."""

from __future__ import annotations

from ..data import config as config_dados

DIR_RESULTADOS = config_dados.DIR_DADOS / "resultados"

# --- Deslocamento a pé ------------------------------------------------------
# Velocidade de caminhada (4,5 km/h) e fator de circuidade, que converte a
# distância em linha reta (haversine) em distância pela rede de ruas
# (Ballou, Rahardja & Sakai, 2002).
VELOCIDADE_M_POR_MIN = 75.0
FATOR_CIRCUIDADE = 1.3
# Lojas do mesmo prédio/galeria: deslocamento fixo.
TEMPO_MESMO_PREDIO_MIN = 1.0
# Valores de `predio` que não agrupam lojas (lojas de rua, avulsas).
PREDIOS_SEM_AGRUPAMENTO = ("rua",)  # primeira palavra do prédio, sem acento/caixa

# --- Função objetivo ----------------------------------------------------------
# Valor do minuto andando: o turista aceita pagar até r US$ a mais para andar
# 1 minuto a menos.
R_PADRAO = 0.25

# --- Janelas de tempo (padrões quando a fonte não informa) ---------------------
ABRE_PADRAO = "07:00"
FECHA_PADRAO = "16:00"
PERMANENCIA_PADRAO_MIN = 20.0

# --- Solver -----------------------------------------------------------------
LIMITE_TEMPO_S = {"pequena": 60, "media": 60, "grande": 300}
LIMITE_TEMPO_PADRAO_S = 60
# Até quantas lojas o polimento da ordem usa o modelo exato (acima disso, 2-opt).
POLIMENTO_EXATO_MAX_LOJAS = 10
LIMITE_TEMPO_POLIMENTO_S = 30

TOL = 1e-6
