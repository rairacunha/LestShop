import datetime as dt
import sqlite3

import pytest
import requests

from lesteshop.data.cotacao import ErroCotacao, obter_cotacao


class Resp:
    def __init__(self, dados):
        self.dados = dados

    def raise_for_status(self):
        pass

    def json(self):
        return self.dados


class SessaoPTAX:
    """Simula a API Olinda: só há PTAX nos dias de ``cotacoes``."""

    def __init__(self, cotacoes: dict[str, float], falhar=False):
        self.cotacoes = cotacoes
        self.falhar = falhar
        self.datas_consultadas = []

    def get(self, url, params=None, timeout=None):
        if self.falhar:
            raise requests.ConnectionError("fora do ar")
        data = params["@dataCotacao"].strip("'")  # MM-DD-YYYY
        self.datas_consultadas.append(data)
        dia = dt.datetime.strptime(data, "%m-%d-%Y").date().isoformat()
        if dia not in self.cotacoes:
            return Resp({"value": []})
        return Resp({"value": [
            {"cotacaoVenda": self.cotacoes[dia] - 0.01, "dataHoraCotacao": f"{dia} 10:00:00.000"},
            {"cotacaoVenda": self.cotacoes[dia], "dataHoraCotacao": f"{dia} 13:04:00.000"},
        ]})


SABADO = dt.date(2026, 10, 17)


def test_fim_de_semana_usa_ultimo_dia_util():
    sessao = SessaoPTAX({"2026-10-16": 5.4321})  # sexta-feira
    cot = obter_cotacao(SABADO, sessao=sessao, hoje=SABADO)
    assert cot.data == "2026-10-16" and cot.valor_brl_por_usd == 5.4321
    assert sessao.datas_consultadas == ["10-17-2026", "10-16-2026"]


def test_feriado_na_sexta_volta_ate_quinta():
    domingo = dt.date(2026, 10, 18)
    cot = obter_cotacao(domingo, sessao=SessaoPTAX({"2026-10-15": 5.40}), hoje=domingo)
    assert cot.data == "2026-10-15"


def test_cache_por_um_dia_na_tabela_cotacoes():
    con = sqlite3.connect(":memory:")
    sessao = SessaoPTAX({"2026-10-16": 5.4321})
    obter_cotacao(sessao=sessao, con=con, hoje=SABADO)
    n = len(sessao.datas_consultadas)
    cot = obter_cotacao(sessao=sessao, con=con, hoje=SABADO)
    assert cot.do_cache and len(sessao.datas_consultadas) == n
    assert con.execute("SELECT data, valor_brl_por_usd FROM cotacoes").fetchall() == [("2026-10-16", 5.4321)]
    # no dia seguinte, consulta de novo
    obter_cotacao(sessao=sessao, con=con, hoje=SABADO + dt.timedelta(days=1))
    assert len(sessao.datas_consultadas) > n


def test_api_fora_do_ar_usa_ultima_guardada_ou_erro():
    with pytest.raises(ErroCotacao, match="Não foi possível consultar a PTAX"):
        obter_cotacao(sessao=SessaoPTAX({}, falhar=True), hoje=SABADO)
    con = sqlite3.connect(":memory:")
    obter_cotacao(sessao=SessaoPTAX({"2026-10-16": 5.43}), con=con, hoje=SABADO)
    cot = obter_cotacao(sessao=SessaoPTAX({}, falhar=True), con=con, hoje=SABADO + dt.timedelta(days=3))
    assert cot.valor_brl_por_usd == 5.43 and "última guardada" in cot.fonte
