import datetime as dt

import pytest

from lesteshop.data.validator import ErroValidacao, validar

HOJE = dt.date(2026, 10, 17)


@pytest.fixture
def base(semente):
    return {k: semente[k].copy() for k in ("lojas", "produtos", "ofertas")}


def _v(base):
    return validar(base["lojas"], base["produtos"], base["ofertas"], hoje=HOJE)


def test_semente_e_valida(base):
    res = _v(base)
    assert res.ok, res.erros


def test_id_repetido(base):
    base["lojas"].loc[1, "loja_id"] = base["lojas"].loc[0, "loja_id"]
    assert any("loja_id repetido" in e for e in _v(base).erros)


def test_oferta_para_loja_ou_produto_inexistente(base):
    base["ofertas"].loc[0, "loja_id"] = "NAO-EXISTE"
    base["ofertas"].loc[1, "produto_id"] = "P99"
    erros = " ".join(_v(base).erros)
    assert "lojas inexistentes: NAO-EXISTE" in erros
    assert "produtos inexistentes: P99" in erros


def test_preco_nao_positivo(base):
    base["ofertas"].loc[0, "preco_usd"] = 0
    assert any("preco_usd deve ser maior que zero" in e for e in _v(base).erros)


def test_oferta_sem_preco_e_descartada_com_alerta(base):
    base["ofertas"].loc[0, "preco_usd"] = None
    res = _v(base)
    assert res.ofertas_sem_preco == 1 and len(res.ofertas) == len(base["ofertas"]) - 1


def test_peso_e_volume(base):
    base["produtos"].loc[0, "peso_kg"] = -1
    base["produtos"].loc[1, "volume_l"] = 0
    erros = " ".join(_v(base).erros)
    assert "peso_kg deve ser maior que zero" in erros and "volume_l deve ser maior que zero" in erros


def test_peso_vazio_e_aceito(base):
    base["produtos"]["peso_kg"] = None
    assert _v(base).ok


def test_coordenada_fora_de_cde(base):
    base["lojas"].loc[0, ["latitude", "longitude"]] = [-25.5163, -54.5854]  # Foz do Iguaçu
    assert any("Coordenadas fora de Ciudad del Este" in e for e in _v(base).erros)


def test_loja_de_outra_cidade(base):
    base["lojas"].loc[0, "cidade"] = "Salto del Guairá"
    assert any("Somente lojas de Ciudad del Este" in e for e in _v(base).erros)


def test_horario_invertido(base):
    base["lojas"].loc[0, ["abre", "fecha"]] = ["17:00", "08:00"]
    assert any("deve ser anterior ao de fechamento" in e for e in _v(base).erros)


def test_horario_mal_formatado(base):
    base["lojas"].loc[0, "abre"] = "7h"
    assert any("formato HH:MM" in e for e in _v(base).erros)


def test_produto_sem_oferta(base):
    base["ofertas"] = base["ofertas"][base["ofertas"]["produto_id"] != "P01"]
    assert any("Produtos sem nenhuma oferta: P01" in e for e in _v(base).erros)


def test_loja_sem_oferta_e_descartada_e_listada(base):
    base["ofertas"] = base["ofertas"][base["ofertas"]["loja_id"] != "S01"]
    base["ofertas"] = base["ofertas"].reset_index(drop=True)
    res = _v(base)
    assert any(l.startswith("S01") for l in res.lojas_descartadas)
    assert "S01" not in set(res.lojas["loja_id"])


def test_alerta_oferta_real_antiga(base):
    base["ofertas"].loc[0, ["tipo_dado", "data_coleta"]] = ["real", "2026-08-01"]
    res = _v(base)
    assert res.ok and any("há mais de 30 dias" in a for a in res.alertas)


def test_tipo_dado_invalido(base):
    base["ofertas"].loc[0, "tipo_dado"] = "chute"
    assert any("tipo_dado inválido" in e for e in _v(base).erros)


def test_levantar_se_invalido(base):
    base["ofertas"].loc[0, "preco_usd"] = -5
    with pytest.raises(ErroValidacao, match="A base de ofertas é inválida"):
        _v(base).levantar_se_invalido()


def test_coluna_faltando(base):
    res = validar(base["lojas"].drop(columns=["cidade"]), base["produtos"], base["ofertas"], hoje=HOJE)
    assert not res.ok and "sem as colunas obrigatórias: cidade" in res.erros[0]


def test_desconto_brasil_fora_de_0_a_1(base):
    base["produtos"].loc[0, "desconto_brasil_pct"] = 28  # deveria ser 0.28
    assert any("desconto_brasil_pct deve estar entre 0 e 1" in e for e in _v(base).erros)
    base["produtos"].loc[0, "desconto_brasil_pct"] = 0.28
    assert _v(base).ok
