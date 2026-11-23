"""Fase 4: base do app, montagem da instância do pedido, apresentação e tela."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest

from lesteshop.app import apresentacao as ap
from lesteshop.app import base as base_app
from lesteshop.app.base import BaseApp, carregar_base, ofertas_antigas, so_mais_recente
from lesteshop.app.pedido import ErroPedido, ItemPedido, montar_pedido, teto_sem_limite, validar_pedido
from lesteshop.data import config, database
from lesteshop.data.cotacao import Cotacao
from lesteshop.data.sources.fonte_csv import FonteCSV
from lesteshop.otimizacao.instancia import carregar_instancia
from lesteshop.otimizacao.resolver import resolver
from lesteshop.otimizacao.solucao import descrever

RAIZ = Path(__file__).resolve().parents[1]
COTACAO = Cotacao("2026-11-18", 5.0, "teste")


@pytest.fixture(scope="module")
def base_ficticia(tmp_path_factory) -> BaseApp:
    # Sempre a base fictícia de data/raw/, mesmo que haja coletas reais em data/coletas/.
    caminho = tmp_path_factory.mktemp("banco") / "lesteshop.db"
    database.recriar_banco(caminho, fontes=[FonteCSV(config.DIR_RAW)]).close()
    return carregar_base(caminho)


def base_da_pasta(pasta: Path) -> BaseApp:
    fonte = FonteCSV(pasta)
    ofertas = so_mais_recente(fonte.carregar_ofertas())
    produtos = fonte.carregar_produtos()
    produtos = produtos[produtos["produto_id"].isin(set(ofertas["produto_id"]))].reset_index(drop=True)
    return BaseApp(lojas=fonte.carregar_lojas(), produtos=produtos, ofertas=ofertas,
                   pontos=fonte.carregar_pontos_partida(), caminho_banco=pasta)


# --- base -----------------------------------------------------------------------
def test_base_ficticia_identificada(base_ficticia):
    assert base_ficticia.origem == "ficticia"
    assert base_ficticia.data_coleta == ("2026-10-26", "2026-10-26")
    assert base_ficticia.n_lojas == 50
    nivel, texto = ap.texto_origem(base_ficticia)
    assert nivel == "atencao" and "FICTÍCIA" in texto


def test_so_produtos_com_oferta(base_ficticia):
    assert set(base_ficticia.produtos["produto_id"]) <= set(base_ficticia.ofertas["produto_id"])
    assert not base_ficticia.produtos.empty


def test_coleta_mais_recente_vale_mesmo_mais_cara():
    of = pd.DataFrame([
        {"loja_id": "L1", "produto_id": "P1", "preco_usd": 10.0, "data_coleta": "2026-10-01", "tipo_dado": "real"},
        {"loja_id": "L1", "produto_id": "P1", "preco_usd": 12.0, "data_coleta": "2026-11-01", "tipo_dado": "real"},
        {"loja_id": "L2", "produto_id": "P1", "preco_usd": 11.0, "data_coleta": "2026-10-01", "tipo_dado": "real"},
    ])
    r = so_mais_recente(of)
    assert sorted(zip(r["loja_id"], r["preco_usd"])) == [("L1", 12.0), ("L2", 11.0)]


def test_origem_real_e_mista(base_ficticia):
    real = BaseApp(base_ficticia.lojas, base_ficticia.produtos,
                   base_ficticia.ofertas.assign(tipo_dado="real"), base_ficticia.pontos, Path("."))
    assert real.origem == "real"
    assert ap.texto_origem(real)[0] == "ok" and "26/10/2026" in ap.texto_origem(real)[1]
    mista = real.ofertas.copy()
    mista.loc[0, "tipo_dado"] = "sintetico"
    assert BaseApp(real.lojas, real.produtos, mista, real.pontos, Path(".")).origem == "mista"


def test_aviso_de_oferta_antiga(base_ficticia):
    pid = base_ficticia.produtos["produto_id"].iloc[0]
    assert ofertas_antigas(base_ficticia, [pid], hoje=dt.date(2026, 11, 1)) == []
    avisos = ofertas_antigas(base_ficticia, [pid], hoje=dt.date(2026, 12, 31))
    assert len(avisos) == 1 and "26/10/2026" in avisos[0]


# --- pedido ---------------------------------------------------------------------
def _ids(base, n):
    return list(base.produtos["produto_id"].iloc[:n])


def test_montar_pedido_sem_orcamento_usa_a_cota(base_ficticia):
    ids = _ids(base_ficticia, 3)
    inst = montar_pedido(base_ficticia, [ItemPedido(ids[0], 2, 5), ItemPedido(ids[1]), ItemPedido(ids[2], 1, 1)],
                         dt.time(9, 0), dt.time(14, 30))
    assert not inst.orcamento_informado and inst.orcamento == inst.cota == 500.0
    assert (inst.chegada, inst.saida) == (540, 870)
    assert [(i.produto_id, i.quantidade, i.prioridade) for i in inst.itens] == \
        [(ids[0], 2, 5), (ids[1], 1, 3), (ids[2], 1, 1)]
    assert inst.n_lojas_instancia == 50 and inst.tamanho is None


def test_montar_pedido_com_orcamento(base_ficticia):
    inst = montar_pedido(base_ficticia, [ItemPedido(_ids(base_ficticia, 1)[0])], "08:00", "16:00", 750.0)
    assert inst.orcamento_informado and inst.orcamento == 750.0


@pytest.mark.parametrize("itens, chegada, saida, orcamento, trecho", [
    ("vazia", "08:00", "16:00", None, "pelo menos um item"),
    ("dup", "08:00", "16:00", None, "mais de uma vez"),
    ("qtd0", "08:00", "16:00", None, "quantidade"),
    ("pri6", "08:00", "16:00", None, "prioridade"),
    ("ok", "16:00", "08:00", None, "saída"),
    ("ok", "08:00", "16:00", 0.0, "orçamento"),
    ("desconhecido", "08:00", "16:00", None, "não está na base"),
])
def test_validacao(base_ficticia, itens, chegada, saida, orcamento, trecho):
    pid = _ids(base_ficticia, 1)[0]
    itens = {"dup": [ItemPedido(pid), ItemPedido(pid)], "qtd0": [ItemPedido(pid, 0)],
             "pri6": [ItemPedido(pid, 1, 6)], "ok": [ItemPedido(pid)],
             "desconhecido": [ItemPedido("XXX")], "vazia": []}[itens]
    erros = validar_pedido(base_ficticia, itens, chegada, saida, orcamento)
    assert any(trecho in e for e in erros)
    with pytest.raises(ErroPedido):
        montar_pedido(base_ficticia, itens, chegada, saida, orcamento)


def test_preco_da_coleta_mais_recente_entra_na_instancia(base_ficticia):
    of = base_ficticia.ofertas
    linha = of.iloc[0]
    antiga = linha.copy()
    antiga["preco_usd"] = 0.01
    antiga["data_coleta"] = "2026-01-01"
    base = BaseApp(base_ficticia.lojas, base_ficticia.produtos,
                   so_mais_recente(pd.concat([of, antiga.to_frame().T], ignore_index=True)),
                   base_ficticia.pontos, Path("."))
    inst = montar_pedido(base, [ItemPedido(linha["produto_id"])], "07:00", "16:00")
    i = next(n for n in inst.nos_lojas if inst.loja(n).loja_id == linha["loja_id"])
    assert inst.preco[(i, 0)] == pytest.approx(float(linha["preco_usd"]))


@pytest.mark.parametrize("nome", ["inst_001_pequena", "inst_045_media"])
def test_pedido_equivale_a_instancia_da_pasta(nome):
    """Montar pelo app a lista de uma instância dá a mesma solução que ler a pasta."""
    pasta = config.DIR_INSTANCIAS / nome
    meta = json.loads((pasta / "metadata.json").read_text(encoding="utf-8"))
    lista = pd.read_csv(pasta / "lista_compras.csv", dtype={"produto_id": str})
    itens = [ItemPedido(r.produto_id, int(r.quantidade), int(r.prioridade)) for r in lista.itertuples()]
    inst_app = montar_pedido(base_da_pasta(pasta), itens, meta["horario_chegada"], meta["horario_saida"],
                             meta.get("orcamento_usd"))
    inst_pasta = carregar_instancia(pasta)
    sol_app, _ = resolver(inst_app)
    sol_pasta, _ = resolver(inst_pasta)
    d_app, d_pasta = descrever(sol_app, inst_app), descrever(sol_pasta, inst_pasta)
    assert d_app["resumo"]["objetivo"] == pytest.approx(d_pasta["resumo"]["objetivo"])
    assert d_app["resumo"]["gasto_produtos"] == pytest.approx(d_pasta["resumo"]["gasto_produtos"])
    compras = lambda d: sorted((p["loja_id"], c["produto_id"]) for p in d["roteiro"] for c in p["compras"])
    assert compras(d_app) == compras(d_pasta)


# --- apresentação ---------------------------------------------------------------
def test_formatos():
    assert ap.fmt_usd(1234.5) == "US$ 1.234,50"
    assert ap.fmt_brl(None) == "—" and ap.fmt_brl(10) == "R$ 10,00"
    assert ap.em_brl(10, COTACAO) == 50.0 and ap.em_brl(10, None) is None
    assert ap.fmt_data("2026-10-26") == "26/10/2026"


def test_tabelas_do_resultado(base_ficticia):
    sem_oferta = base_ficticia.produtos["produto_id"].iloc[0]
    # Tira as ofertas de um item para ele aparecer como "sem oferta".
    base = BaseApp(base_ficticia.lojas, base_ficticia.produtos,
                   base_ficticia.ofertas[base_ficticia.ofertas["produto_id"] != sem_oferta],
                   base_ficticia.pontos, Path("."))
    ids = _ids(base_ficticia, 4)
    inst = montar_pedido(base, [ItemPedido(p) for p in ids], "08:00", "16:00")
    sol, _ = resolver(inst)
    d = descrever(sol, inst)
    itens = ap.tabela_itens(d, base, COTACAO)
    assert len(itens) == d["resumo"]["itens_comprados"]
    assert set(itens["Preço"]) == {"fictício (teste)"} and itens["Total (R$)"].str.startswith("R$").all()
    rot = ap.tabela_roteiro(d)
    assert rot.iloc[0]["Onde"].startswith("Ponte") and rot.iloc[-1]["Chega às"] == d["horario_retorno"]
    fora = ap.tabela_fora(d, inst)
    assert "nenhuma loja" in fora.set_index("Produto").loc[base_ficticia.nome_produto(sem_oferta), "Por quê"]
    totais = ap.totais(d, COTACAO)
    assert [t[0] for t in totais] == ["Produtos", "Imposto da Receita", "Total a pagar"]
    f = ap.resumo_fiscal(d, COTACAO)
    assert "Portaria" in f["cota"] and f["premissa"]


def test_resumo_fiscal_com_limite_ultrapassado(base_ficticia):
    # 4 pendrives + 4 mouses + 4 fones = 12 unidades de "demais bens" (limite 10, e
    # 3 idênticos): a bagagem perde a cota. Caso pequeno, rápido em qualquer sistema.
    itens = [ItemPedido(p, 4, 5) for p in ("P034", "P031", "P009")]
    inst = montar_pedido(base_ficticia, itens, "08:00", "16:00", 2000.0)
    sol, _ = resolver(inst)
    d = descrever(sol, inst)
    f = ap.resumo_fiscal(d, COTACAO)
    assert f["imposto_sem_cota"] and "R$" in f["imposto_sem_cota"]
    assert f["declaracao"].startswith("Sim")
    assert "ACIMA do limite" in set(ap.tabela_limites(d["fiscal"])["Situação"])


def test_texto_solver():
    assert ap.texto_solver({"info": {"status": "otimo"}}) is None
    texto = ap.texto_solver({"info": {"status": "viavel (limite de tempo)", "gap": 0.039}})
    assert "tempo limite" in texto and "3,9%" in texto
    assert "ótimo" not in texto and "gap" not in texto  # Fase 5: sem termos técnicos


# --- tela -----------------------------------------------------------------------
def test_tela_calcula_roteiro(base_ficticia, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(base_app, "carregar_base", lambda *a, **k: base_ficticia)
    monkeypatch.setattr(base_app, "cotacao_para_exibir", lambda *a, **k: COTACAO)
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=120)
    at.run()
    assert not at.exception
    at.run()  # sem tela: só a base guardada, sem opção a escolher
    assert any("FICTÍCIA" in w.value for w in at.warning)
    pid = base_ficticia.produtos["produto_id"].iloc[1]
    at.text_input(key="busca_produto").input(base_ficticia.nome_produto(pid)).run()
    next(b for b in at.button if b.key == f"add_{pid}").click().run()
    assert at.number_input(key=f"qtd_{pid}").value == 1
    next(b for b in at.button if b.label == "Calcular meu roteiro").click().run()
    assert not at.exception
    textos = " ".join(m.value for m in at.markdown)
    assert "Seu roteiro" in textos and "Receita Federal" in textos
    assert "Quanto você vai pagar" in textos and "Onde comprar" in textos
    rotulos = [m.label for m in at.metric]
    assert rotulos[:4] == ["Total a pagar", "Você economiza", "Volta à Ponte", "Cota da Receita"]
    assert len(at.get("deck_gl_json_chart")) == 1, "o mapa do roteiro deve aparecer"
    assert len(at.dataframe) >= 2


def test_preco_atipico_e_descartado_com_aviso():
    of = pd.DataFrame({"loja_id": ["A", "B", "C", "D"], "produto_id": ["P"] * 4,
                       "titulo_oferta": ["iPad", "iPad", "iPad", "Fone G-Tide"],
                       "preco_usd": [449.0, 455.0, 440.0, 9.0]})
    ficam, avisos = base_app.descartar_precos_atipicos(of, {"P": "iPad 11"})
    assert list(ficam["loja_id"]) == ["A", "B", "C"]
    assert "Fone G-Tide (US$ 9,00)" in avisos["P"][0] and "iPad 11" in avisos["P"][0]
    # Com menos de 3 ofertas não há mediana confiável: nada é descartado.
    assert len(base_app.descartar_precos_atipicos(of.iloc[2:])[0]) == 2


def test_cotacao_do_site_vem_das_ofertas():
    of = pd.DataFrame({"preco_usd": [80.0, 100.0, 0.0], "preco_brl": [476.0, 595.0, 10.0],
                       "data_coleta": ["2026-11-19", "2026-11-20", "2026-11-20"]})
    c = base_app.cotacao_do_site(of)
    assert c.valor_brl_por_usd == 5.95 and c.data == "2026-11-20" and "Compras Paraguai" in c.fonte
    assert base_app.cotacao_do_site(of.assign(preco_brl=None)) is None


def test_orcamento_so_referencia_todos_os_itens_entram(base_ficticia):
    """Decidido em 20/11/2026: no app, o orçamento não corta itens (só avisa)."""
    caros = (base_ficticia.ofertas.groupby("produto_id")["preco_usd"].min()
             .sort_values(ascending=False).index[:3].tolist())
    itens = [ItemPedido(p, 1, 1) for p in caros]
    inst = montar_pedido(base_ficticia, itens, "07:00", "16:00", teto_sem_limite(base_ficticia, itens))
    d = descrever(resolver(inst)[0], inst)
    assert d["nao_comprados"] == [] and d["resumo"]["custo_total"] > 500
    aviso = ap.aviso_orcamento(d, 500.0, COTACAO)
    assert aviso and "passa do seu orçamento de US$ 500,00" in aviso and "R$" in aviso
    assert ap.aviso_orcamento(d, None, None) is None
    assert ap.aviso_orcamento(d, d["resumo"]["custo_total"] + 1, None) is None
    # Com a regra antiga (B = cota), algum item ficaria de fora.
    inst_cota = montar_pedido(base_ficticia, itens, "07:00", "16:00")
    assert descrever(resolver(inst_cota)[0], inst_cota)["nao_comprados"]



def test_comparativo_avulsa_shopping_china(base_ficticia):
    ids = _ids(base_ficticia, 5)
    itens = [ItemPedido(p) for p in ids]
    inst = montar_pedido(base_ficticia, itens, "07:00", "16:00", teto_sem_limite(base_ficticia, itens))
    d = descrever(resolver(inst)[0], inst)
    # Base fictícia não tem o Shopping China: tudo pelo preço médio das lojas.
    c = ap.comparativo_avulsa(d, inst, base_ficticia)
    assert c["referencia"] == "preço médio das lojas" and len(c["na_media"]) == len(c["tabela"])
    assert c["custo_rota"] == pytest.approx(d["resumo"]["custo_total"])
    assert c["economia_pct"] == pytest.approx(c["economia"] / c["custo_avulsa"])
    # Com uma loja de referência (a primeira do roteiro), os itens dela usam o preço dela.
    ref = d["roteiro"][0]["loja_id"]
    c2 = ap.comparativo_avulsa(d, inst, base_ficticia, loja_ref=ref)
    nome_ref = d["roteiro"][0]["nome"]
    assert c2["referencia"] == nome_ref
    assert (c2["tabela"]["Avulsa: onde"] == nome_ref).sum() >= len(d["roteiro"][0]["compras"])


def test_versao_web_esconde_a_consulta_ao_vivo(monkeypatch):
    from lesteshop.app import tela

    monkeypatch.delenv("LESTESHOP_CONSULTA", raising=False)
    monkeypatch.setattr(tela.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert not tela.tem_tela()          # servidor (Streamlit Cloud, Codespaces)
    monkeypatch.setattr(tela.sys, "platform", "win32")
    assert tela.tem_tela()              # notebook com Windows
    monkeypatch.setenv("LESTESHOP_CONSULTA", "0")
    assert not tela.tem_tela()
    assert ap.fmt_pct(0.1234) == "12,3%"


# --- Fase 5: resumo no topo e mapa ---------------------------------------------------
def test_resumo_topo_e_dados_do_mapa(base_ficticia):
    ids = _ids(base_ficticia, 5)
    itens = [ItemPedido(p) for p in ids]
    inst = montar_pedido(base_ficticia, itens, "07:00", "16:00", teto_sem_limite(base_ficticia, itens))
    d = descrever(resolver(inst)[0], inst)
    c = ap.comparativo_avulsa(d, inst, base_ficticia)
    topo = ap.resumo_topo(d, c, COTACAO)
    assert [t["rotulo"] for t in topo] == ["Total a pagar", "Você economiza", "Volta à Ponte", "Cota da Receita"]
    assert topo[0]["valor"].startswith("R$") and topo[2]["valor"] == d["horario_retorno"]
    assert topo[3]["valor"] == ("Dentro da cota" if d["resumo"]["excedente"] <= 0 else "Passa da cota")
    assert ap.resumo_topo(d, c, None)[0]["valor"].startswith("US$")

    m = ap.dados_mapa(d, inst, base_ficticia)
    pts = m["pontos"]
    assert pts.iloc[0]["numero"] == "P" and pts.iloc[0]["tipo"] == "ponte"
    # Cada loja do roteiro aparece num ponto (lojas no mesmo endereço ficam juntas).
    assert len(pts) >= 2 and pts["numero"].iloc[1:].str.len().gt(0).all()
    # Ponte -> lojas -> Ponte, em linha reta.
    assert len(m["trechos"]) == len(d["roteiro"]) + 1
    assert m["trechos"][0]["de"] == m["trechos"][-1]["para"] == (pts.iloc[0]["lat"], pts.iloc[0]["lon"])
    assert all(c["nome"] in " ".join(pts["comprar"]) for p in d["roteiro"] for c in p["compras"])
    assert ap.dados_mapa({**d, "roteiro": []}, inst, base_ficticia) is None


def test_mapa_junta_lojas_no_mesmo_predio(base_ficticia):
    ids = _ids(base_ficticia, 1)
    inst = montar_pedido(base_ficticia, [ItemPedido(ids[0])], "07:00", "16:00")
    d = descrever(resolver(inst)[0], inst)
    p = d["roteiro"][0]
    p = {**p, "predio": "Galería X"}
    vizinha = {**p, "ordem": 2, "nome": "Loja vizinha", "compras": [{**p["compras"][0], "nome": "Outro"}]}
    terceira = {**vizinha, "ordem": 3, "nome": "Loja 3"}
    m = ap.dados_mapa({**d, "roteiro": [p, vizinha, terceira]}, inst, base_ficticia)
    assert list(m["pontos"]["numero"]) == ["P", "1-3"]
    assert ap._rotulo_numeros([1, 4]) == "1,4" and ap._rotulo_numeros([2]) == "2"
    assert m["pontos"].iloc[1]["nome"].startswith("Galería X: 1.") and "Loja vizinha" in m["pontos"].iloc[1]["nome"]
