"""Cache local da consulta sob demanda (SQLite, validade em horas).

Guarda, para cada item do catálogo, o resultado já extraído (produto, lojas e
ofertas) e o momento da consulta. Dentro da validade (6 h), o app usa o cache e
não acessa o site. As páginas de loja (endereço e coordenadas) têm um cache
próprio, permanente, em ``data/cache/lojas/`` (ver ``FonteComprasParaguai``).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from . import config

_SQL = """
CREATE TABLE IF NOT EXISTS consultas (
    item_id TEXT PRIMARY KEY,
    gravado_em REAL NOT NULL,   -- segundos desde 1970 (UTC)
    dados TEXT NOT NULL          -- JSON: produto, lojas, ofertas, consultado_em
)
"""


class CacheConsulta:
    def __init__(self, caminho: str | Path = config.CAMINHO_CACHE,
                 validade_h: float = config.VALIDADE_CACHE_H, agora=time.time):
        self.caminho = Path(caminho)
        self.validade_s = validade_h * 3600
        self.agora = agora
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.execute(_SQL)

    def _con(self) -> sqlite3.Connection:
        return sqlite3.connect(self.caminho)

    def obter(self, item_id: str) -> dict | None:
        """Dados do item se ainda estiverem na validade; senão ``None``."""
        with self._con() as con:
            linha = con.execute("SELECT gravado_em, dados FROM consultas WHERE item_id = ?", (item_id,)).fetchone()
        if linha is None or self.agora() - linha[0] > self.validade_s:
            return None
        return json.loads(linha[1])

    def gravar(self, item_id: str, dados: dict) -> None:
        with self._con() as con:
            con.execute("INSERT OR REPLACE INTO consultas VALUES (?, ?, ?)",
                        (item_id, self.agora(), json.dumps(dados, ensure_ascii=False)))

    def limpar(self) -> None:
        with self._con() as con:
            con.execute("DELETE FROM consultas")
