"""Cotação PTAX de venda (Banco Central, serviço Olinda).

Todos os cálculos do LesteShop são feitos em US$; a cotação serve apenas para
exibir valores em R$.

Uso pela linha de comando::

    python -m lesteshop.data.cotacao            # cotação de hoje (ou último dia útil)
    python -m lesteshop.data.cotacao 2026-10-17
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sqlite3
from dataclasses import dataclass

import requests

from . import config

log = logging.getLogger(__name__)

URL_PTAX = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarDia(dataCotacao=@dataCotacao)"
)
FONTE_PTAX = "Banco Central do Brasil - PTAX venda (Olinda)"

SQL_TABELA = """
CREATE TABLE IF NOT EXISTS cotacoes (
    data TEXT PRIMARY KEY,
    valor_brl_por_usd REAL NOT NULL CHECK (valor_brl_por_usd > 0),
    fonte TEXT NOT NULL,
    data_consulta TEXT NOT NULL
)
"""


class ErroCotacao(RuntimeError):
    """Não foi possível obter a cotação (API fora do ar e sem cache)."""


@dataclass
class Cotacao:
    data: str  # data da PTAX usada (AAAA-MM-DD)
    valor_brl_por_usd: float
    fonte: str
    do_cache: bool = False

    def __str__(self) -> str:
        origem = " (cache)" if self.do_cache else ""
        return f"US$ 1 = R$ {self.valor_brl_por_usd:.4f} em {self.data} - {self.fonte}{origem}"


def _consultar_dia(dia: dt.date, sessao) -> float | None:
    params = {
        "@dataCotacao": f"'{dia:%m-%d-%Y}'",
        "$top": "100",
        "$format": "json",
        "$select": "cotacaoVenda,dataHoraCotacao",
    }
    resp = sessao.get(URL_PTAX, params=params, timeout=30)
    resp.raise_for_status()
    valores = resp.json().get("value", [])
    if not valores:
        return None  # fim de semana ou feriado: o BCB não publica PTAX
    ultimo = max(valores, key=lambda v: v.get("dataHoraCotacao", ""))
    return float(ultimo["cotacaoVenda"])


def obter_cotacao(
    data: dt.date | None = None,
    con: sqlite3.Connection | None = None,
    sessao=None,
    max_dias_atras: int = 10,
    hoje: dt.date | None = None,
) -> Cotacao:
    """PTAX de venda da ``data`` (padrão: hoje) ou do último dia útil anterior.

    Com ``con``, a cotação fica guardada na tabela ``cotacoes`` e é reaproveitada
    durante o dia da consulta, sem acessar a API de novo.
    """
    hoje = hoje or dt.date.today()
    data = data or hoje
    if con is not None:
        con.execute(SQL_TABELA)
        linha = con.execute(
            "SELECT data, valor_brl_por_usd, fonte FROM cotacoes "
            "WHERE data_consulta = ? AND data <= ? AND data >= ? ORDER BY data DESC LIMIT 1",
            (hoje.isoformat(), data.isoformat(), (data - dt.timedelta(days=max_dias_atras)).isoformat()),
        ).fetchone()
        if linha and data == hoje:
            return Cotacao(linha[0], float(linha[1]), linha[2], do_cache=True)

    sessao = sessao or requests.Session()
    try:
        for atras in range(max_dias_atras + 1):
            dia = data - dt.timedelta(days=atras)
            valor = _consultar_dia(dia, sessao)
            if valor is not None:
                if atras:
                    log.info("Sem PTAX em %s; usando a do último dia útil, %s.", data, dia)
                cot = Cotacao(dia.isoformat(), valor, FONTE_PTAX)
                if con is not None:
                    con.execute(
                        "INSERT OR REPLACE INTO cotacoes VALUES (?, ?, ?, ?)",
                        (cot.data, cot.valor_brl_por_usd, cot.fonte, hoje.isoformat()),
                    )
                    con.commit()
                return cot
        raise ErroCotacao(f"O Banco Central não publicou PTAX entre {dia} e {data}.")
    except (requests.RequestException, ValueError, KeyError) as e:
        if con is not None:
            linha = con.execute(
                "SELECT data, valor_brl_por_usd, fonte FROM cotacoes WHERE data <= ? ORDER BY data DESC LIMIT 1",
                (data.isoformat(),),
            ).fetchone()
            if linha:
                log.warning("API PTAX indisponível (%s); usando a última cotação guardada (%s).", e, linha[0])
                return Cotacao(linha[0], float(linha[1]), linha[2] + " - última guardada", do_cache=True)
        motivo = "sem conexão com olinda.bcb.gov.br" if isinstance(e, requests.ConnectionError) else str(e)[:200]
        raise ErroCotacao(f"Não foi possível consultar a PTAX no Banco Central ({motivo}).") from e


def usd_para_brl(valor_usd: float, cotacao: Cotacao) -> float:
    """Apenas para exibição."""
    return round(valor_usd * cotacao.valor_brl_por_usd, 2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consulta a PTAX de venda do dólar.")
    parser.add_argument("data", nargs="?", help="AAAA-MM-DD (padrão: hoje)")
    parser.add_argument("--banco", default=str(config.CAMINHO_BANCO))
    args = parser.parse_args(argv)
    data = dt.date.fromisoformat(args.data) if args.data else None
    con = sqlite3.connect(args.banco) if args.banco else None
    try:
        print(obter_cotacao(data, con=con))
    except ErroCotacao as e:
        print(f"ERRO: {e}")
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
