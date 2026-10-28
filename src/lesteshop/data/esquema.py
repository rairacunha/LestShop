"""Formato comum das tabelas (seção 2). Toda fonte devolve DataFrames assim."""

from __future__ import annotations

import pandas as pd

COLUNAS: dict[str, list[str]] = {
    "lojas": [
        "loja_id", "nome", "slug", "cidade", "endereco", "predio", "latitude",
        "longitude", "coordenada_pendente", "abre", "fecha",
        "tempo_permanencia_min", "fonte", "tipo_dado",
    ],
    "produtos": [
        "produto_id", "nome", "categoria", "url_modelo", "peso_kg", "volume_l",
        "desconto_brasil_pct", "tipo_dado",
    ],
    "ofertas": [
        "loja_id", "produto_id", "titulo_oferta", "codigo_loja", "preco_usd",
        "preco_brl", "data_coleta", "fonte", "tipo_dado",
    ],
    "pontos_partida": ["id", "nome", "latitude", "longitude"],
    "catalogo_modelos": ["modelo_id", "nome", "url", "categoria", "data_atualizacao"],
    "cotacoes": ["data", "valor_brl_por_usd", "fonte"],
}

_NUMERICAS = {
    "lojas": ["latitude", "longitude", "tempo_permanencia_min"],
    "produtos": ["peso_kg", "volume_l", "desconto_brasil_pct"],
    "ofertas": ["preco_usd", "preco_brl"],
    "pontos_partida": ["latitude", "longitude"],
    "cotacoes": ["valor_brl_por_usd"],
}
_TEXTO = {
    "lojas": ["loja_id", "nome", "slug", "cidade", "endereco", "predio", "abre",
              "fecha", "fonte", "tipo_dado"],
    "produtos": ["produto_id", "nome", "categoria", "url_modelo", "tipo_dado"],
    "ofertas": ["loja_id", "produto_id", "titulo_oferta", "codigo_loja",
                "data_coleta", "fonte", "tipo_dado"],
    "catalogo_modelos": ["modelo_id", "nome", "url", "categoria", "data_atualizacao"],
}


def _vazio(valor: object) -> bool:
    return valor is None or (not isinstance(valor, str) and bool(pd.isna(valor)))


def _para_bool(valor: object) -> bool:
    if isinstance(valor, bool):
        return valor
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return False
    return str(valor).strip().lower() in {"1", "true", "verdadeiro", "sim", "t", "yes"}


def vazio(tabela: str) -> pd.DataFrame:
    return padronizar(pd.DataFrame(columns=COLUNAS[tabela]), tabela)


def padronizar(df: pd.DataFrame, tabela: str) -> pd.DataFrame:
    """Garante colunas na ordem certa e tipos coerentes (sem alterar valores)."""
    df = df.copy()
    for col in COLUNAS[tabela]:
        if col not in df.columns:
            df[col] = None
    extras = [c for c in df.columns if c not in COLUNAS[tabela]]
    df = df[COLUNAS[tabela] + extras]
    for col in _NUMERICAS.get(tabela, []):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    for col in _TEXTO.get(tabela, []):
        valores = [None if _vazio(v) else (str(v).strip() or None) for v in df[col].tolist()]
        df[col] = pd.Series(valores, index=df.index, dtype=object)
    if tabela == "lojas":
        df["coordenada_pendente"] = df["coordenada_pendente"].map(_para_bool).astype(bool)
    return df.reset_index(drop=True)
