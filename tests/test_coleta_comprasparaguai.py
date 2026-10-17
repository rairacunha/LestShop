import datetime as dt
import logging

import pytest

from lesteshop.data import config
from lesteshop.data.sources import FonteComprasParaguai, FonteDeOfertas
from lesteshop.data.sources.http import ErroColeta
from lesteshop.data.validator import validar

HOJE = dt.date(2026, 10, 17)


@pytest.fixture
def fonte(cliente_falso, tmp_path):
    return FonteComprasParaguai(termos=["playstation 5 pro"], cliente=cliente_falso,
                                dir_cache_lojas=tmp_path / "lojas", hoje=HOJE)


def test_fonte_implementa_a_interface(fonte):
    assert isinstance(fonte, FonteDeOfertas)


def test_filtro_mantem_somente_ciudad_del_este(fonte, caplog):
    with caplog.at_level(logging.INFO):
        res = fonte.coletar()
    assert set(res.lojas["slug"]) == {"eletro-leste", "games-del-este", "importados-ponte"}
    assert (res.lojas["cidade"] == "Ciudad del Este").all()
    assert len(res.ofertas) == 3
    # Guaíra Tech (Salto del Guairá) e PJC Games (Pedro Juan Caballero) descartadas
    assert res.descartadas_por_cidade == {"Salto del Guairá": 1, "Pedro Juan Caballero": 1}
    assert "2 descartadas por cidade" in caplog.text


def test_loja_de_outra_cidade_indicada_na_oferta_nem_e_acessada(fonte, cliente_falso):
    fonte.coletar()
    assert not any("pjc-games" in u for u in cliente_falso.sessao_falsa.acessos)


def test_dados_gravados_com_fonte_data_e_tipo_real(fonte):
    res = fonte.coletar()
    assert (res.ofertas["fonte"] == config.FONTE_CP).all()
    assert (res.ofertas["data_coleta"] == "2026-10-17").all()
    assert (res.ofertas["tipo_dado"] == "real").all()
    assert (res.lojas["tipo_dado"] == "real").all()
    produto = res.produtos.iloc[0]
    assert produto["produto_id"] == "CP-51234" and produto["peso_kg"] == 4.6


def test_coordenadas_e_predio(fonte):
    lojas = fonte.coletar().lojas.set_index("slug")
    assert not lojas.loc["eletro-leste", "coordenada_pendente"]
    assert lojas.loc["games-del-este", "coordenada_pendente"]
    assert lojas.loc["eletro-leste", "predio"] == "Shopping Exemplo Paraná"
    assert lojas.loc["importados-ponte", "predio"] == "Edificio Exemplo Sul"


def test_coleta_passa_na_validacao(fonte):
    res = fonte.coletar()
    assert validar(res.lojas, res.produtos, res.ofertas, hoje=HOJE).ok


def test_boa_conduta_user_agent_intervalo_robots_e_cache(fonte, cliente_falso, tmp_path):
    fonte.coletar()
    sessao = cliente_falso.sessao_falsa
    assert sessao.acessos[0].endswith("/robots.txt")
    assert all("LesteShop" in h["User-Agent"] and "academico" in h["User-Agent"] for h in sessao.headers_usados)
    assert cliente_falso.esperas and all(s >= 10 - 1e-9 for s in cliente_falso.esperas)
    assert len(cliente_falso.esperas) == len(sessao.acessos) - 1
    # mesma página no mesmo dia vem do cache, sem nova requisição
    n = len(sessao.acessos)
    FonteComprasParaguai(termos=["playstation 5 pro"], cliente=cliente_falso,
                         dir_cache_lojas=tmp_path / "lojas", hoje=HOJE).coletar()
    assert len(sessao.acessos) == n


def test_loja_nao_e_baixada_duas_vezes(fonte, cliente_falso):
    fonte.coletar()
    acessos = cliente_falso.sessao_falsa.acessos
    assert acessos.count(f"{config.URL_BASE_CP}/lojas/eletro-leste/") == 1


def test_robots_txt_proibindo_interrompe(cliente_falso, tmp_path):
    (tmp_path / "robots").mkdir()
    proibido = tmp_path / "robots" / "robots.txt"
    proibido.write_text("User-agent: *\nDisallow: /\n")
    cliente_falso.sessao_falsa.rotas[f"{config.URL_BASE_CP}/robots.txt"] = str(proibido)
    fonte = FonteComprasParaguai(termos=["playstation 5 pro"], cliente=cliente_falso,
                                 dir_cache_lojas=tmp_path / "lojas", hoje=HOJE)
    with pytest.raises(ErroColeta, match="robots.txt proíbe"):
        fonte.coletar()
