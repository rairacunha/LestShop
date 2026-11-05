"""Testes da Fase 2: modelo de otimização (TPP + mochila + cota + imposto + janelas)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from lesteshop.data import config as config_dados
from lesteshop.otimizacao import config
from lesteshop.otimizacao.distancias import haversine_m, matriz_tempos
from lesteshop.otimizacao.heuristica import resolver_heuristica
from lesteshop.otimizacao.instancia import carregar_instancia
from lesteshop.otimizacao.modelo import resolver_exato
from lesteshop.otimizacao.resolver import main as resolver_main
from lesteshop.otimizacao.resolver import resolver
from lesteshop.otimizacao.rota import agenda, polir_rota, tempo_andando
from lesteshop.otimizacao.solucao import Solucao, avaliar, descrever

PONTE = (-25.5097, -54.6033)
# 1 minuto a pé ≈ 75 m / 1,3 (circuidade) ≈ 57,7 m em linha reta ≈ 0,000519° de latitude
GRAU_POR_MIN = 75.0 / config.FATOR_CIRCUIDADE / 111_195.0


def _loja(lid, minutos_ao_sul, predio=None, abre="07:00", fecha="17:00", perm=10, pendente=False,
          minutos_a_oeste=0.0):
    return {
        "loja_id": lid, "nome": f"Loja {lid}", "slug": lid.lower(), "cidade": "Ciudad del Este",
        "endereco": "", "predio": predio,
        "latitude": None if pendente else PONTE[0] - minutos_ao_sul * GRAU_POR_MIN,
        "longitude": None if pendente else PONTE[1] - minutos_a_oeste * GRAU_POR_MIN / 0.9027,
        "coordenada_pendente": pendente, "abre": abre, "fecha": fecha,
        "tempo_permanencia_min": perm, "fonte": "teste", "tipo_dado": "sintetico",
    }


def criar_instancia(pasta: Path, lojas, ofertas, lista, **meta) -> Path:
    """Escreve uma instância mínima no formato da Fase 1."""
    pasta.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(lojas).to_csv(pasta / "lojas.csv", index=False)
    produtos = sorted({o[1] for o in ofertas} | {l[0] for l in lista})
    pd.DataFrame([{
        "produto_id": p, "nome": f"Produto {p}", "categoria": "Teste", "url_modelo": "",
        "peso_kg": meta.pop(f"peso_{p}", 1.0), "volume_l": 2.0, "tipo_dado": "sintetico",
    } for p in produtos]).to_csv(pasta / "produtos.csv", index=False)
    pd.DataFrame([{
        "loja_id": l, "produto_id": p, "titulo_oferta": p, "codigo_loja": "", "preco_usd": preco,
        "preco_brl": preco * 5, "data_coleta": "2026-11-05", "fonte": "teste", "tipo_dado": "sintetico",
    } for l, p, preco in ofertas]).to_csv(pasta / "ofertas.csv", index=False)
    pd.DataFrame([{"id": 0, "nome": "Ponte", "latitude": PONTE[0], "longitude": PONTE[1]}]).to_csv(
        pasta / "pontos_partida.csv", index=False)
    pd.DataFrame([{"produto_id": p, "nome": f"Produto {p}", "quantidade": q, "prioridade": v}
                  for p, v, q in lista]).to_csv(pasta / "lista_compras.csv", index=False)
    base = {"nome": pasta.name, "tamanho": "pequena", "n_lojas": len(lojas),
            "cota_disponivel_usd": 500.0, "aliquota_excedente": 0.5, "orcamento_usd": 2000.0,
            "horario_chegada": "08:00", "horario_saida": "16:00", "tipo_dado": "sintetico"}
    base.update(meta)
    (pasta / "metadata.json").write_text(json.dumps(base), encoding="utf-8")
    return pasta


def _exato(inst, r=config.R_PADRAO):
    res = resolver_exato(inst, r, limite_s=30)
    assert res.status == "otimo"
    return res.solucao, avaliar(res.solucao, inst)


# --- Distâncias -------------------------------------------------------------

def test_haversine_um_grau_de_latitude():
    assert haversine_m(0, 0, 1, 0) == pytest.approx(111_195, rel=1e-3)


def test_matriz_tempos_predio_e_circuidade():
    coords = [PONTE, (PONTE[0] - 10 * GRAU_POR_MIN, PONTE[1]), (PONTE[0] - 10.2 * GRAU_POR_MIN, PONTE[1]),
              (PONTE[0] - 20 * GRAU_POR_MIN, PONTE[1]), (PONTE[0] - 20.2 * GRAU_POR_MIN, PONTE[1])]
    t = matriz_tempos(coords, [None, "Galeria X", "galeria x", "Rua (loja de rua)", "Rua (loja de rua)"])
    assert t[0, 1] == pytest.approx(10.0, rel=1e-3)          # haversine × 1,3 ÷ 75
    assert t[1, 2] == config.TEMPO_MESMO_PREDIO_MIN           # mesmo prédio
    assert t[3, 4] == config.TEMPO_MESMO_PREDIO_MIN           # perto, mas não agrupa: piso de 1 min
    assert t[1, 3] == pytest.approx(10.0, rel=1e-3)
    assert (t == t.T).all()


# --- Cota, imposto e mochila --------------------------------------------------

def test_imposto_lista_acima_da_cota(tmp_path):
    p = criar_instancia(tmp_path / "i", [_loja("A", 5)], [("A", "P1", 400.0), ("A", "P2", 200.0)],
                        [("P1", 5, 1), ("P2", 4, 1)], orcamento_usd=1000.0)
    inst = carregar_instancia(p)
    sol, av = _exato(inst)
    assert len(sol.compras) == 2
    assert av.gasto_produtos == pytest.approx(600.0)
    assert av.imposto == pytest.approx(0.5 * max(0.0, 600.0 - 500.0))
    assert av.custo_total == pytest.approx(650.0)
    assert "excede a cota em US$ 100.00" in descrever(sol, inst)["situacao_cota"]


def test_orcamento_inclui_imposto_e_mochila_corta_menor_prioridade(tmp_path):
    # 600 + 50 de imposto = 650 > 640: não cabem os dois; fica o de prioridade 5.
    p = criar_instancia(tmp_path / "i", [_loja("A", 5)], [("A", "P1", 400.0), ("A", "P2", 200.0)],
                        [("P1", 5, 1), ("P2", 4, 1)], orcamento_usd=640.0)
    sol, av = _exato(carregar_instancia(p))
    assert set(sol.compras) == {0}
    assert av.imposto == 0.0


def test_prioridade_domina_custo_e_tempo(tmp_path):
    # Um item caro de prioridade 3 contra dois baratos de prioridade 1 (só cabe um grupo).
    p = criar_instancia(tmp_path / "i", [_loja("A", 5), _loja("B", 30)],
                        [("B", "P1", 290.0), ("A", "P2", 150.0), ("A", "P3", 150.0)],
                        [("P1", 3, 1), ("P2", 1, 1), ("P3", 1, 1)], orcamento_usd=300.0)
    inst = carregar_instancia(p)
    for r in (0.0, 0.25, 1.0):
        lam = inst.lambda_(r)
        assert lam * (inst.orcamento + r * inst.t_max) < 1.0
        sol, av = _exato(inst, r)
        assert av.prioridade_total == 3


def test_quantidade_multiplica_preco(tmp_path):
    p = criar_instancia(tmp_path / "i", [_loja("A", 5)], [("A", "P1", 100.0)], [("P1", 2, 3)])
    _, av = _exato(carregar_instancia(p))
    assert av.gasto_produtos == pytest.approx(300.0)


def test_sem_orcamento_teto_e_a_cota(tmp_path):
    p = criar_instancia(tmp_path / "i", [_loja("A", 5)], [("A", "P1", 300.0), ("A", "P2", 250.0)],
                        [("P1", 3, 1), ("P2", 2, 1)], cota_disponivel_usd=500.0)
    inst = carregar_instancia(p, orcamento=None)
    assert inst.orcamento == 500.0 and not inst.orcamento_informado
    sol, av = _exato(inst)
    assert set(sol.compras) == {0} and av.imposto == 0.0


# --- r, janelas de tempo, big-M ------------------------------------------------

def test_r_troca_gasto_por_caminhada(tmp_path):
    # Mesmo item: perto (5 min) por US$ 100 ou longe (30 min) por US$ 95.
    # Ida e volta a mais ≈ 50 min: com r = 0 compra longe, com r = 1 compra perto.
    p = criar_instancia(tmp_path / "i", [_loja("PERTO", 5), _loja("LONGE", 30)],
                        [("PERTO", "P1", 100.0), ("LONGE", "P1", 95.0)], [("P1", 3, 1)])
    inst = carregar_instancia(p)
    perto = next(i for i in inst.nos_lojas if inst.loja(i).loja_id == "PERTO")
    longe = next(i for i in inst.nos_lojas if inst.loja(i).loja_id == "LONGE")
    assert _exato(inst, 0.0)[0].compras[0] == longe
    assert _exato(inst, 1.0)[0].compras[0] == perto


def test_janela_de_tempo_impede_loja_que_fecha(tmp_path):
    # A loja barata fica a 10 min e fecha 08:25; chegando 08:10 com 20 min de permanência, não dá.
    p = criar_instancia(tmp_path / "i",
                        [_loja("BARATA", 10, fecha="08:25", perm=20), _loja("CARA", 12)],
                        [("BARATA", "P1", 50.0), ("CARA", "P1", 80.0)], [("P1", 4, 1)])
    inst = carregar_instancia(p)
    sol, av = _exato(inst)
    assert inst.loja(sol.compras[0]).loja_id == "CARA"
    assert av.viavel
    # Chegando mais cedo, a barata volta a ser possível.
    p2 = criar_instancia(tmp_path / "j",
                         [_loja("BARATA", 10, fecha="08:25", perm=20), _loja("CARA", 12)],
                         [("BARATA", "P1", 50.0), ("CARA", "P1", 80.0)], [("P1", 4, 1)],
                         horario_chegada="07:30")
    inst2 = carregar_instancia(p2)
    sol2, _ = _exato(inst2)
    assert inst2.loja(sol2.compras[0]).loja_id == "BARATA"


def test_espera_abertura_e_volta_ate_a_saida(tmp_path):
    p = criar_instancia(tmp_path / "i", [_loja("A", 10, abre="09:00", perm=30)], [("A", "P1", 10.0)],
                        [("P1", 2, 1)], horario_saida="09:45")
    inst = carregar_instancia(p)
    ag = agenda([1], inst)
    assert ag.inicio[0] == 9 * 60                    # espera abrir
    assert ag.retorno == pytest.approx(9 * 60 + 30 + 10, abs=0.1)
    assert ag.viavel
    p2 = criar_instancia(tmp_path / "j", [_loja("A", 10, abre="09:00", perm=30)], [("A", "P1", 10.0)],
                         [("P1", 2, 1)], horario_saida="09:35")
    inst2 = carregar_instancia(p2)
    sol, av = _exato(inst2)
    assert sol.compras == {} and av.objetivo == 0.0   # não dá para voltar a tempo: compra nada


def test_big_m_menor_valor_da_formula(tmp_path):
    p = criar_instancia(tmp_path / "i", [_loja("A", 5, abre="07:00", fecha="15:00", perm=10),
                                         _loja("B", 20, abre="09:00", fecha="17:00", perm=25)],
                        [("A", "P1", 10.0), ("B", "P2", 10.0)], [("P1", 1, 1), ("P2", 1, 1)])
    inst = carregar_instancia(p)
    # Janelas recortadas por [08:00, 16:00]: min(abre)=08:00, max(fecha)=16:00
    esperado = 16 * 60 + 25 + inst.t.max() - 8 * 60
    assert inst.big_m() == pytest.approx(esperado)
    assert resolver_exato(inst, limite_s=30).big_m == pytest.approx(esperado)


# --- Pré-processamento ---------------------------------------------------------

def test_coordenada_pendente_avisa_itens_perdidos(tmp_path):
    p = criar_instancia(tmp_path / "i", [_loja("A", 5), _loja("SEMCOORD", 3, pendente=True)],
                        [("A", "P1", 100.0), ("SEMCOORD", "P1", 50.0), ("SEMCOORD", "P2", 20.0)],
                        [("P1", 3, 1), ("P2", 2, 1)])
    inst = carregar_instancia(p)
    assert [l.loja_id for l in inst.lojas] == ["A"]
    assert inst.lojas_excluidas[0]["itens"] == ["Produto P1", "Produto P2"]
    texto = " ".join(inst.avisos)
    assert "SEMCOORD" in texto and "Produto P1" in texto and "Produto P2" in texto
    assert "não tem oferta disponível" in texto                 # P2 só existia lá
    sol, _ = _exato(inst)
    assert set(sol.compras) == {0}


def test_oferta_repetida_usa_menor_preco(tmp_path):
    p = criar_instancia(tmp_path / "i", [_loja("A", 5)], [("A", "P1", 120.0), ("A", "P1", 99.0)],
                        [("P1", 3, 1)])
    inst = carregar_instancia(p)
    assert inst.preco[(1, 0)] == 99.0
    assert any("repetida" in a for a in inst.avisos)


def test_padroes_de_horario_quando_vazios(tmp_path):
    loja = _loja("A", 5, abre=None, fecha=None, perm=None)
    p = criar_instancia(tmp_path / "i", [loja], [("A", "P1", 10.0)], [("P1", 1, 1)],
                        horario_chegada="06:00", horario_saida="18:00")
    l = carregar_instancia(p).loja(1)
    assert (l.abre, l.fecha, l.permanencia) == (7 * 60, 16 * 60, config.PERMANENCIA_PADRAO_MIN)


# --- Bagagem -----------------------------------------------------------------

def test_bagagem_opcional_desligada_por_padrao(tmp_path):
    p = criar_instancia(tmp_path / "i", [_loja("A", 5)], [("A", "P1", 50.0), ("A", "P2", 40.0)],
                        [("P1", 3, 1), ("P2", 2, 1)], peso_P1=8.0, peso_P2=5.0)
    _, av = _exato(carregar_instancia(p))
    assert av.itens_comprados == 2 and av.peso_kg == pytest.approx(13.0)
    sol, av = _exato(carregar_instancia(p, peso_max_kg=10.0))
    assert set(sol.compras) == {0} and av.peso_kg <= 10.0


# --- Heurística, polimento e instâncias reais -------------------------------------

def test_polimento_reordena_rota_ruim(tmp_path):
    lojas = [_loja(f"L{n}", 3 * n) for n in range(1, 5)] + [_loja(f"W{n}", 3 * n, minutos_a_oeste=8)
                                                           for n in range(1, 9)]
    ofertas = [(l["loja_id"], f"P{n}", 10.0) for n, l in enumerate(lojas)]
    lista = [(f"P{n}", 1, 1) for n in range(len(lojas))]
    inst = carregar_instancia(criar_instancia(tmp_path / "i", lojas, ofertas, lista,
                                              horario_saida="20:00"))
    for tamanho in (6, len(lojas)):                      # exato (≤ 10 lojas) e 2-opt (> 10)
        rota = list(inst.nos_lojas)[:tamanho]
        ruim = rota[::2] + rota[1::2]
        pol = polir_rota(ruim, inst)
        assert pol.metodo == ("exato" if tamanho <= 10 else "2-opt")
        assert sorted(pol.rota) == sorted(ruim)
        assert agenda(pol.rota, inst).viavel
        assert pol.tempo_andando_depois <= pol.tempo_andando_antes
        assert pol.tempo_andando_depois == pytest.approx(tempo_andando(pol.rota, inst))


INSTANCIAS_AMOSTRA = ["inst_001_pequena", "inst_012_pequena", "inst_045_media", "inst_090_grande"]


@pytest.mark.parametrize("nome", INSTANCIAS_AMOSTRA)
def test_instancias_da_base_ficticia(nome):
    inst = carregar_instancia(config_dados.DIR_INSTANCIAS / nome)
    final, heur = resolver(inst, config.R_PADRAO)
    af, ah = avaliar(final, inst), avaliar(heur, inst)
    assert af.viavel and ah.viavel
    assert final.info["status"] == "otimo" and final.info["gap"] == 0.0
    assert ah.objetivo <= af.objetivo + 1e-6
    assert af.objetivo == pytest.approx(final.info["objetivo_modelo"], abs=1e-6)
    assert af.imposto == pytest.approx(inst.aliquota * max(0.0, af.gasto_produtos - inst.cota), abs=0.01)
    assert af.custo_total <= inst.orcamento + 1e-6
    assert final.info["tempo_andando_depois_polimento"] <= final.info["tempo_andando_antes_polimento"] + 1e-9


def test_heuristica_sozinha_e_viavel():
    inst = carregar_instancia(config_dados.DIR_INSTANCIAS / "inst_100_grande")
    assert avaliar(resolver_heuristica(inst), inst).viavel


def test_comando_resolver_grava_json(tmp_path, capsys):
    saida = tmp_path / "sol.json"
    assert resolver_main([str(config_dados.DIR_INSTANCIAS / "inst_001_pequena"), "--json", str(saida)]) == 0
    d = json.loads(saida.read_text(encoding="utf-8"))
    assert d["roteiro"] and "situacao_cota" in d
    assert "Situação da cota" in capsys.readouterr().out
