"""Barra "economizar ↔ andar menos" e recálculo durante o passeio (23/11/2026)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from lesteshop.app import base as base_app
from lesteshop.app import passeio as ps
from lesteshop.app.base import carregar_base
from lesteshop.app.pedido import ItemPedido, montar_pedido, teto_sem_limite
from lesteshop.data import config, database
from lesteshop.data.cotacao import Cotacao
from lesteshop.data.sources.fonte_csv import FonteCSV
from lesteshop.otimizacao.resolver import resolver
from lesteshop.otimizacao.solucao import descrever

RAIZ = Path(__file__).resolve().parents[1]
COTACAO = Cotacao("2026-11-18", 5.0, "teste")
PONTE = (-25.5097, -54.6033)
CENTRO_CDE = (-25.5105, -54.6110)


@pytest.fixture(scope="module")
def base_ficticia(tmp_path_factory):
    caminho = tmp_path_factory.mktemp("banco") / "lesteshop.db"
    database.recriar_banco(caminho, fontes=[FonteCSV(config.DIR_RAW)]).close()
    return carregar_base(caminho)


@pytest.fixture(scope="module")
def calculo(base_ficticia):
    itens = [ItemPedido(p) for p in base_ficticia.produtos["produto_id"].iloc[:5]]
    inst = montar_pedido(base_ficticia, itens, "08:00", "16:00", teto_sem_limite(base_ficticia, itens))
    sol, _ = resolver(inst)
    return inst, descrever(sol, inst)


@pytest.mark.parametrize("lat, lon, dentro", [
    (*PONTE, True), (*CENTRO_CDE, True),
    (-25.5469, -54.5882, False),   # Foz do Iguaçu
    (-25.2637, -57.5759, False),   # Assunção
    (None, None, False),
])
def test_dentro_de_ciudad_del_este(lat, lon, dentro):
    assert ps.em_ciudad_del_este(lat, lon) is dentro


def test_instancia_do_passeio(calculo):
    inst, d = calculo
    primeira = d["roteiro"][0]
    i2, feito = ps.instancia_do_passeio(inst, d, {primeira["loja_id"]}, *CENTRO_CDE, 600)
    comprados = {c["produto_id"] for c in primeira["compras"]}
    assert {it.produto_id for it in i2.itens} == {it.produto_id for it in inst.itens} - comprados
    assert feito == pytest.approx(sum(c["preco_usd"] * c["quantidade"] for c in primeira["compras"]))
    assert i2.cota == pytest.approx(max(0.0, inst.cota - feito)) and i2.chegada == 600
    # Ida sai da posição atual; volta continua indo para a Ponte.
    assert i2.m == inst.m  # às 10:00 todas as lojas ainda estão abertas
    assert (i2.t[:, 0] == inst.t[:, 0]).all() and not (i2.t[0, 1:] == inst.t[0, 1:]).all()
    assert all(k < len(i2.itens) for _, k in i2.preco)
    d2 = descrever(resolver(i2)[0], i2)
    assert d2["horario_chegada"] == "10:00" and d2["roteiro"][0]["chegada"] >= "10:00"
    t = ps.totais_do_passeio(feito, d2, inst)
    total = feito + d2["resumo"]["gasto_produtos"]
    assert t["imposto"] == pytest.approx(inst.aliquota * max(0.0, total - inst.cota))
    # Com cota reduzida, o imposto do recálculo é exatamente o que falta pagar.
    assert t["imposto"] == pytest.approx(inst.aliquota * max(0.0, feito - inst.cota)
                                         + d2["resumo"]["imposto"], abs=0.02)


def test_passeio_tarde_demais_nao_quebra(calculo):
    inst, d = calculo
    i2, _ = ps.instancia_do_passeio(inst, d, set(), *CENTRO_CDE, 15 * 60 + 55)
    assert i2.m < inst.m and all(l.abre <= l.fecha for l in i2.lojas)  # lojas fechando saem
    d2 = descrever(resolver(i2)[0], i2)
    assert d2["horario_retorno"] <= "16:00"


def test_barra_economizar_andar_menos(calculo):
    """r maior nunca aumenta o tempo andando (análise de sensibilidade da Fase 2)."""
    inst, _ = calculo
    andando = [descrever(resolver(inst, r=r)[0], inst)["resumo"]["tempo_andando"] for r in (0.0, 1.0)]
    assert andando[1] <= andando[0] + 1e-6


def _app(base_ficticia, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(base_app, "carregar_base", lambda *a, **k: base_ficticia)
    monkeypatch.setattr(base_app, "cotacao_para_exibir", lambda *a, **k: COTACAO)
    monkeypatch.setattr(ps, "agora_no_paraguai",
                        lambda: dt.datetime(2026, 11, 23, 10, 0, tzinfo=ps.FUSO_PARAGUAI))
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=120)
    at.run()
    at.radio(key="modo").set_value("Base guardada").run()
    for pid in base_ficticia.produtos["produto_id"].iloc[:3]:
        at.text_input(key="busca_produto").input(base_ficticia.nome_produto(pid)).run()
        next(b for b in at.button if b.key == f"add_{pid}").click().run()
    at.select_slider(key="valor_minuto").set_value(1.0).run()
    next(b for b in at.button if b.label == "Calcular meu roteiro").click().run()
    assert not at.exception
    return at


def test_tela_passeio_exige_localizacao_em_cde(base_ficticia, monkeypatch):
    pytest.importorskip("streamlit")
    at = _app(base_ficticia, monkeypatch)
    assert at.session_state["resultado"]["r"] == 1.0
    assert any("Usar minha localização" in i.value for i in at.info)       # sem localização
    at.session_state["posicao_teste"] = {"erro": "A localização está desativada ou o acesso foi negado."}
    at.run()
    assert any("Ative a localização" in w.value for w in at.warning)
    at.session_state["posicao_teste"] = {"lat": -25.5469, "lon": -54.5882, "precisao": 20}  # Foz
    at.run()
    assert any("não está em Ciudad del Este" in w.value for w in at.warning)
    assert not any(b.label == "Recalcular a rota a partir daqui" for b in at.button)


def test_tela_passeio_recalcula(base_ficticia, monkeypatch):
    pytest.importorskip("streamlit")
    at = _app(base_ficticia, monkeypatch)
    primeira = at.session_state["resultado"]["d"]["roteiro"][0]["loja_id"]
    at.multiselect(key="passeio_feitas").set_value([primeira])
    at.session_state["posicao_teste"] = {"lat": CENTRO_CDE[0], "lon": CENTRO_CDE[1], "precisao": 15}
    at.run()
    assert any("Localização ativa em Ciudad del Este" in s.value and "10:00" in s.value for s in at.success)
    next(b for b in at.button if b.label == "Recalcular a rota a partir daqui").click().run()
    assert not at.exception
    assert "Sua nova rota" in " ".join(m.value for m in at.markdown)
    assert [m.label for m in at.metric][-3:] == ["Já gastou", "Falta gastar", "Total da viagem, com imposto"]
