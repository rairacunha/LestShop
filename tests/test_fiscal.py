"""Testes da Fase 3: regras fiscais e de bagagem (cota, limites quantitativos, alertas).

Casos montados à mão para cada regra: abaixo do limite, exatamente no limite,
acima do limite, mistura de categorias e itens idênticos. Os limites são só
alertas: a solução do modelo não muda.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from lesteshop.fiscal.categorias import carregar_categorias
from lesteshop.fiscal.regras import ErroRegras, carregar_regras, ler_tabela
from lesteshop.fiscal.verificacao import ItemCesta, verificar
from lesteshop.otimizacao.instancia import carregar_instancia
from lesteshop.otimizacao.modelo import resolver_exato
from lesteshop.otimizacao.solucao import avaliar, descrever

from test_otimizacao import _loja, criar_instancia

HOJE = date(2026, 11, 17)


@pytest.fixture(scope="module")
def regras():
    return carregar_regras(data=HOJE)


def item(pid, n=1, preco=50.0, cat="outros", conteudo=None, nome=None):
    return ItemCesta(pid, nome or f"Produto {pid}", cat, n, preco, conteudo)


def checar(itens, regras, aliquota=0.5):
    gasto = sum(it.preco_unitario * it.quantidade for it in itens)
    imposto = aliquota * max(0.0, gasto - regras.cota_usd)
    return verificar(itens, regras, gasto, aliquota, imposto)


def situacao(res, regra_id):
    return next(s for s in res["limites"] if s["regra_id"] == regra_id)


# --- Tabela de regras -------------------------------------------------------------

def test_cota_terrestre_vigente_e_500(regras):
    assert regras.cota_usd == 500.0
    assert "Portaria ME 601/2019" in regras.cota.fonte
    assert regras.via == "terrestre"


def test_aliquota_do_rte_vem_da_tabela(regras):
    assert regras.aliquota_rte == 0.5
    assert "art. 12" in regras.aliquota.fonte
    assert "aliquota_rte" not in {r.regra_id for r in regras.limites}


def test_tabela_versionada_usa_a_vigencia_da_data():
    assert carregar_regras(data="2019-12-31").cota_usd == 300.0
    assert carregar_regras(data="2020-01-01").cota_usd == 500.0


def test_tabela_tem_todos_os_limites_do_levantamento(regras):
    ids = {r.regra_id for r in regras.limites}
    assert ids == {"bebidas", "cigarros", "charutos", "fumo", "pequeno_valor_total",
                   "pequeno_valor_identicos", "outros_total", "outros_identicos"}
    for r in ler_tabela():
        assert r.fonte and r.vigencia_inicio <= HOJE


def _tabela(tmp_path, linhas):
    base = pd.read_csv(carregar_regras.__defaults__[0], dtype=str, keep_default_na=False)
    # cota de US$ 500 e alíquota em vigor + as linhas do teste
    vigentes = base[base["regra_id"].isin(["cota_terrestre", "aliquota_rte"])].iloc[1:]
    df = pd.concat([vigentes] + [pd.DataFrame([l]) for l in linhas], ignore_index=True)
    caminho = tmp_path / "regras.csv"
    df.to_csv(caminho, index=False)
    return caminho


def test_tabela_invalida_e_recusada(tmp_path):
    ruim = _tabela(tmp_path, [{"regra_id": "x", "tipo_limite": "peso", "categoria_fiscal": "outros",
                               "contagem": "total", "limite": "1", "unidade": "kg", "via": "terrestre",
                               "valor_unitario_min_usd": "", "valor_unitario_max_usd": "",
                               "consequencia": "perde_cota", "descricao": "x", "fonte": "x",
                               "vigencia_inicio": "2020-01-01"}])
    with pytest.raises(ErroRegras, match="tipo_limite"):
        carregar_regras(ruim, data=HOJE)


def test_vigencia_duplicada_e_recusada(tmp_path):
    base = pd.read_csv(carregar_regras.__defaults__[0], dtype=str, keep_default_na=False)
    dup = base[base["regra_id"] == "cota_terrestre"].iloc[-1].to_dict()
    with pytest.raises(ErroRegras, match="mesma vigência"):
        carregar_regras(_tabela(tmp_path, [dup]), data=HOJE)


def test_aliquota_fora_de_0_a_1_e_recusada(tmp_path):
    base = pd.read_csv(carregar_regras.__defaults__[0], dtype=str, keep_default_na=False)
    ruim = base[base["regra_id"] != "aliquota_rte"].copy()
    linha = base[base["regra_id"] == "aliquota_rte"].iloc[0].to_dict() | {"limite": "1.5"}
    caminho = tmp_path / "r.csv"
    pd.concat([ruim, pd.DataFrame([linha])]).to_csv(caminho, index=False)
    with pytest.raises(ErroRegras, match="entre 0 e 1"):
        carregar_regras(caminho, data=HOJE)


def test_sem_cota_em_vigor_e_erro():
    with pytest.raises(ErroRegras, match="cota_terrestre"):
        carregar_regras(data="2000-01-01")


# --- Mapeamento de categorias -------------------------------------------------------

def test_mapeamento_por_categoria_e_por_produto():
    mapa = carregar_categorias()
    assert mapa.classificar("P001", "Informática").categoria_fiscal == "outros"
    whisky = mapa.classificar("P050", "Bebidas")
    assert whisky.categoria_fiscal == "bebidas_alcoolicas" and whisky.conteudo_por_unidade == 1.0
    assert mapa.classificar("P051", "Bebidas").conteudo_por_unidade == 0.75
    desconhecida = mapa.classificar("PX", "Jardinagem")
    assert desconhecida.categoria_fiscal == "outros" and "Jardinagem" in desconhecida.aviso


def test_todas_as_categorias_da_base_estao_mapeadas():
    mapa = carregar_categorias()
    produtos = pd.read_csv("data/raw/produtos.csv", dtype=str)
    for _, p in produtos.iterrows():
        c = mapa.classificar(p["produto_id"], p["categoria"])
        assert not c.aviso
        if c.categoria_fiscal == "bebidas_alcoolicas":
            assert c.conteudo_por_unidade, p["produto_id"]


# --- Demais bens (≥ US$ 5): 10 unidades no total, no máximo 3 idênticas -------------

@pytest.mark.parametrize("n_itens, esperado", [(9, "abaixo"), (10, "no_limite"), (11, "acima")])
def test_outros_total(regras, n_itens, esperado):
    res = checar([item(f"P{k}", preco=30.0) for k in range(n_itens)], regras)
    s = situacao(res, "outros_total")
    assert s["usado"] == n_itens and s["limite"] == 10 and s["situacao"] == esperado
    assert res["perde_cota"] is (esperado == "acima")


@pytest.mark.parametrize("n, esperado", [(2, "abaixo"), (3, "no_limite"), (4, "acima")])
def test_outros_identicos_em_lote(regras, n, esperado):
    # oferta em lote: quantidade n do mesmo produto (y_k continua binário)
    res = checar([item("P1", n=n, preco=40.0), item("P2", preco=40.0)], regras)
    s = situacao(res, "outros_identicos")
    assert s["usado"] == n and s["produto_id"] == "P1" and s["situacao"] == esperado


def test_perda_da_cota_mostra_imposto_sem_cota(regras):
    # 4 idênticos de US$ 100 = US$ 400: dentro da cota, mas acima do limite de 3 idênticos.
    res = checar([item("P1", n=4, preco=100.0)], regras)
    assert res["perde_cota"] and res["limites_ultrapassados"] == ["outros_identicos"]
    assert res["imposto_modelo_usd"] == 0.0
    assert res["imposto_sem_cota_usd"] == pytest.approx(200.0)
    assert any("perde a cota" in a and "US$ 200,00" in a for a in res["alertas"])
    assert res["declaracao_necessaria"]


def test_dentro_dos_limites_nao_ha_imposto_sem_cota(regras):
    res = checar([item("P1", n=3, preco=100.0)], regras)
    assert not res["perde_cota"] and res["imposto_sem_cota_usd"] is None
    assert res["alertas"] == [] and not res["declaracao_necessaria"]


# --- Bens de valor unitário < US$ 5: 20 unidades, no máximo 10 idênticas -------------

def test_pequeno_valor_usa_o_limiar_de_5_dolares(regras):
    res = checar([item("P1", n=10, preco=4.99), item("P2", n=1, preco=5.0)], regras)
    assert situacao(res, "pequeno_valor_identicos")["situacao"] == "no_limite"
    assert situacao(res, "pequeno_valor_total")["usado"] == 10
    # o item de US$ 5,00 conta nos demais bens, não nos de pequeno valor
    assert situacao(res, "outros_total")["usado"] == 1
    assert res["alertas"] == []


@pytest.mark.parametrize("n, esperado", [(19, "abaixo"), (20, "no_limite"), (21, "acima")])
def test_pequeno_valor_total(regras, n, esperado):
    res = checar([item(f"P{k}", preco=2.0) for k in range(n)], regras)
    assert situacao(res, "pequeno_valor_total")["situacao"] == esperado


def test_pequeno_valor_identicos_acima(regras):
    res = checar([item("P1", n=11, preco=1.0)], regras)
    assert situacao(res, "pequeno_valor_identicos")["situacao"] == "acima"
    assert res["perde_cota"]


# --- Bebidas alcoólicas: 12 litros -------------------------------------------------------

@pytest.mark.parametrize("garrafas, esperado", [(11, "abaixo"), (12, "no_limite"), (13, "acima")])
def test_bebidas_em_litros(regras, garrafas, esperado):
    res = checar([item("P050", n=garrafas, preco=38.0, cat="bebidas_alcoolicas", conteudo=1.0)], regras)
    s = situacao(res, "bebidas")
    assert s["usado"] == garrafas and s["situacao"] == esperado
    assert res["excesso_regime_comum"] == (["bebidas"] if esperado == "acima" else [])
    # bebida não entra nos limites de unidades dos demais bens
    assert not any(x["regra_id"] == "outros_total" for x in res["limites"])


def test_bebidas_soma_garrafas_de_tamanhos_diferentes(regras):
    res = checar([item("P050", n=6, preco=38.0, cat="bebidas_alcoolicas", conteudo=1.0),
                  item("P051", n=8, preco=95.0, cat="bebidas_alcoolicas", conteudo=0.75)], regras)
    s = situacao(res, "bebidas")
    assert s["usado"] == pytest.approx(12.0) and s["situacao"] == "no_limite"


def test_excesso_de_bebidas_e_so_alerta_de_regime_comum(regras):
    res = checar([item("P050", n=13, preco=38.0, cat="bebidas_alcoolicas", conteudo=1.0)], regras)
    alerta = next(a for a in res["alertas"] if "Bebidas" in a)
    assert "regime comum" in alerta and "1 L" in alerta
    assert "não compre" not in alerta.lower()
    assert not res["perde_cota"]  # o excesso de bebida não tira a cota dos demais bens


def test_bebida_sem_litros_informados_gera_aviso(regras):
    res = checar([item("PX", n=2, preco=20.0, cat="bebidas_alcoolicas")], regras)
    assert situacao(res, "bebidas")["usado"] == 0
    assert any("conteúdo" in a for a in res["avisos"])


# --- Tabaco (regras na tabela, sem produtos na base) ---------------------------------

def test_cigarros_charutos_e_fumo(regras):
    res = checar([item("C1", n=2, preco=30.0, cat="cigarros", conteudo=10),          # 2 pentes de 10 maços
                  item("H1", n=25, preco=6.0, cat="charutos_cigarrilhas"),
                  item("F1", n=1, preco=20.0, cat="fumo", conteudo=250)], regras)
    assert situacao(res, "cigarros")["usado"] == 20 and situacao(res, "cigarros")["situacao"] == "acima"
    assert situacao(res, "charutos")["situacao"] == "no_limite"
    assert situacao(res, "fumo")["situacao"] == "no_limite"
    assert res["excesso_regime_comum"] == ["cigarros"]


# --- Mistura de categorias e declaração ----------------------------------------------

def test_mistura_de_categorias(regras):
    itens = ([item(f"P{k}", preco=60.0) for k in range(8)]
             + [item("P050", n=3, preco=38.0, cat="bebidas_alcoolicas", conteudo=1.0),
                item("P099", n=5, preco=3.0)])
    res = checar(itens, regras)
    assert situacao(res, "outros_total")["usado"] == 8
    assert situacao(res, "bebidas")["usado"] == 3
    assert situacao(res, "pequeno_valor_total")["usado"] == 5
    assert res["limites_ultrapassados"] == []
    gasto = 8 * 60 + 3 * 38 + 5 * 3
    assert gasto > 500 and res["declaracao_necessaria"]
    assert any("passa da cota" in a for a in res["alertas"])


def test_declaracao_so_quando_excede_cota_ou_limite(regras):
    assert not checar([item("P1", preco=500.0)], regras)["declaracao_necessaria"]
    assert checar([item("P1", preco=500.01)], regras)["declaracao_necessaria"]


def test_premissa_da_periodicidade_sempre_presente(regras):
    res = checar([], regras)
    assert "1 (um) mês" in res["premissa"] and res["limites"] == []


# --- Integração com o modelo da Fase 2 -------------------------------------------------

def test_cota_e_aliquota_vem_da_tabela_e_campos_antigos_sao_ignorados(tmp_path):
    p = criar_instancia(tmp_path / "i", [_loja("A", 5)], [("A", "P1", 100.0)], [("P1", 3, 1)],
                        cota_disponivel_usd=150.0, aliquota_excedente=0.8)
    inst = carregar_instancia(p, regras=carregar_regras(data=HOJE))
    assert inst.cota == 500.0 and inst.aliquota == 0.5
    assert any("cota_disponivel_usd" in a for a in inst.avisos)
    assert any("aliquota_excedente" in a for a in inst.avisos)


def test_instancias_da_base_nao_tem_mais_campos_fiscais():
    for meta in sorted(__import__("pathlib").Path("data/instances").glob("inst_*/metadata.json")):
        campos = json.loads(meta.read_text(encoding="utf-8"))
        assert "cota_disponivel_usd" not in campos and "aliquota_excedente" not in campos, meta


def test_limites_nao_mudam_a_solucao_e_aparecem_em_descrever(tmp_path):
    # 4 unidades idênticas (lote) + 1 item: o modelo compra tudo; o alerta aparece depois.
    p = criar_instancia(tmp_path / "i", [_loja("A", 5)], [("A", "P1", 50.0), ("A", "P2", 80.0)],
                        [("P1", 5, 4), ("P2", 3, 1)], orcamento_usd=1000.0)
    inst = carregar_instancia(p, regras=carregar_regras(data=HOJE))
    res = resolver_exato(inst, 0.25, limite_s=30)
    assert set(res.solucao.compras) == {0, 1}
    av = avaliar(res.solucao, inst)
    assert av.gasto_produtos == pytest.approx(280.0) and av.imposto == 0.0
    fiscal = descrever(res.solucao, inst)["fiscal"]
    assert fiscal["limites_ultrapassados"] == ["outros_identicos"]
    assert fiscal["imposto_sem_cota_usd"] == pytest.approx(140.0)
    assert fiscal["declaracao_necessaria"]


def test_bebidas_da_base_contam_em_litros(tmp_path):
    p = criar_instancia(tmp_path / "i", [_loja("A", 5)], [("A", "P051", 95.0)], [("P051", 5, 2)])
    pd.DataFrame([{"produto_id": "P051", "nome": "Whisky 18 anos 750ml", "categoria": "Bebidas",
                   "url_modelo": "", "peso_kg": 1.4, "volume_l": 1.3, "tipo_dado": "sintetico"}]
                 ).to_csv(p / "produtos.csv", index=False)
    inst = carregar_instancia(p, regras=carregar_regras(data=HOJE))
    assert inst.itens[0].categoria_fiscal == "bebidas_alcoolicas"
    res = resolver_exato(inst, 0.25, limite_s=30)
    s = next(x for x in descrever(res.solucao, inst)["fiscal"]["limites"] if x["regra_id"] == "bebidas")
    assert s["usado"] == pytest.approx(1.5)  # 2 × 0,75 L (não o volume da embalagem)
