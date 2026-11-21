"""Acréscimo por forma de pagamento (aprovado em 21/11/2026)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lesteshop.app import apresentacao as ap
from lesteshop.app import base as base_app
from lesteshop.app.base import carregar_base
from lesteshop.app.pagamento import carregar_formas, com_acrescimo
from lesteshop.app.pedido import ItemPedido, montar_pedido, teto_sem_limite
from lesteshop.data import config, database
from lesteshop.data.cotacao import Cotacao
from lesteshop.data.sources.fonte_csv import FonteCSV
from lesteshop.otimizacao.resolver import resolver
from lesteshop.otimizacao.solucao import descrever

RAIZ = Path(__file__).resolve().parents[1]
COTACAO = Cotacao("2026-11-18", 5.0, "teste")


@pytest.fixture(scope="module")
def base_ficticia(tmp_path_factory):
    caminho = tmp_path_factory.mktemp("banco") / "lesteshop.db"
    database.recriar_banco(caminho, fontes=[FonteCSV(config.DIR_RAW)]).close()
    return carregar_base(caminho)


def test_formas_de_pagamento_do_arquivo():
    formas = {fp.forma_id: fp for fp in carregar_formas()}
    assert {k: fp.acrescimo for k, fp in formas.items()} == {"dinheiro": 0.0, "pix": 0.03, "cartao": 0.06}
    assert [k for k, fp in formas.items() if fp.padrao] == ["pix"]
    assert all("observação de campo" in fp.origem.lower() for fp in formas.values())
    assert formas["pix"].rotulo == "PIX (+3%)" and "sem acréscimo" in formas["dinheiro"].rotulo


@pytest.mark.parametrize("linhas, trecho", [
    (["pix,PIX,0.03,sim,x,2026-11-21"], "sem acréscimo"),
    (["dinheiro,Dinheiro,0,nao,x,2026-11-21", "pix,PIX,0.03,nao,x,2026-11-21"], "padrão"),
    (["dinheiro,Dinheiro,0,sim,x,2026-11-21", "pix,PIX,3,nao,x,2026-11-21"], "entre 0 e 1"),
])
def test_arquivo_invalido(tmp_path, linhas, trecho):
    arq = tmp_path / "formas.csv"
    arq.write_text("forma_id,nome,acrescimo,padrao,origem,data_referencia\n" + "\n".join(linhas) + "\n",
                   encoding="utf-8")
    with pytest.raises(ValueError, match=trecho):
        carregar_formas(arq)


def _pedido(base, n):
    itens = [ItemPedido(p) for p in base.produtos["produto_id"].iloc[:n]]
    inst = montar_pedido(base, itens, "07:00", "16:00", teto_sem_limite(base, itens))
    sol, _ = resolver(inst)
    return inst, sol


def test_imposto_sobre_o_valor_com_acrescimo_e_mesmas_lojas(base_ficticia):
    inst, sol = _pedido(base_ficticia, 4)
    d0 = descrever(sol, inst)
    d6 = descrever(sol, com_acrescimo(inst, 0.06))
    # Roteiro e lojas não mudam.
    assert [p["loja_id"] for p in d6["roteiro"]] == [p["loja_id"] for p in d0["roteiro"]]
    assert d6["horario_retorno"] == d0["horario_retorno"]
    g0 = d0["resumo"]["gasto_produtos"]
    assert d6["resumo"]["gasto_produtos"] == pytest.approx(g0 * 1.06, abs=0.01)
    # Imposto sobre o valor com a taxa (valor da nota fiscal).
    assert d6["resumo"]["imposto"] == pytest.approx(inst.aliquota * max(0.0, g0 * 1.06 - inst.cota), abs=0.01)
    assert com_acrescimo(inst, 0.0) is inst


def test_acrescimo_pode_passar_da_cota(base_ficticia):
    # Compra entre US$ 472 e 499: em dinheiro fica dentro da cota; com o cartão (+6%), passa.
    menor = base_ficticia.ofertas.groupby("produto_id")["preco_usd"].min()
    pid, q = next((p, q) for q in (1, 2, 3) for p, v in menor.items() if 472 < v * q < 499)
    itens = [ItemPedido(pid, q)]
    inst = montar_pedido(base_ficticia, itens, "07:00", "16:00", teto_sem_limite(base_ficticia, itens))
    sol, _ = resolver(inst)
    assert descrever(sol, inst)["resumo"]["imposto"] == 0
    d = descrever(sol, com_acrescimo(inst, 0.06))
    assert d["resumo"]["excedente"] > 0 and d["resumo"]["imposto"] > 0
    assert d["fiscal"]["declaracao_necessaria"]


def test_comparativo_usa_a_mesma_taxa(base_ficticia):
    inst, sol = _pedido(base_ficticia, 4)
    d0 = descrever(sol, inst)
    c0 = ap.comparativo_avulsa(d0, inst, base_ficticia)
    inst3 = com_acrescimo(inst, 0.03)
    d3 = descrever(sol, inst3)
    c3 = ap.comparativo_avulsa(d3, inst3, base_ficticia, acrescimo=0.03)
    assert c3["gasto_rota"] == pytest.approx(c0["gasto_rota"] * 1.03)
    assert c3["gasto_avulsa"] == pytest.approx(c0["gasto_avulsa"] * 1.03)
    assert c3["custo_rota"] == pytest.approx(d3["resumo"]["custo_total"], abs=0.01)


def test_texto_do_custo_a_mais():
    assert "sem acréscimo" in ap.texto_pagamento("Dinheiro", 0.0, 100.0, 100.0, COTACAO)
    t = ap.texto_pagamento("Cartão de crédito", 0.06, 1060.0, 1000.0, COTACAO)
    assert "+6%" in t and "US$ 60,00" in t and "R$ 300,00" in t and "a mais" in t


def test_tela_forma_de_pagamento(base_ficticia, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(base_app, "carregar_base", lambda *a, **k: base_ficticia)
    monkeypatch.setattr(base_app, "cotacao_para_exibir", lambda *a, **k: COTACAO)
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=120)
    at.run()
    at.radio(key="modo").set_value("Base guardada").run()
    assert at.radio(key="forma_pagamento").value.forma_id == "pix"  # PIX por padrão
    pid = base_ficticia.produtos["produto_id"].iloc[1]
    at.text_input(key="busca_produto").input(base_ficticia.nome_produto(pid)).run()
    next(b for b in at.button if b.key == f"add_{pid}").click().run()
    next(b for b in at.button if b.label == "Calcular meu roteiro").click().run()
    assert not at.exception
    textos = " ".join(m.value for m in at.markdown)
    assert "PIX" in textos and "a mais" in textos
    total_pix = at.metric[0].value
    # Trocar a forma de pagamento refaz os valores sem recalcular o roteiro.
    dinheiro = next(fp for fp in carregar_formas() if fp.forma_id == "dinheiro")
    at.radio(key="forma_pagamento").set_value(dinheiro).run()
    assert not at.exception
    assert "sem acréscimo" in " ".join(m.value for m in at.markdown)
    assert at.metric[0].value != total_pix
