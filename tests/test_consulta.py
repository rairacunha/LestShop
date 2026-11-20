"""Fase 4: consulta sob demanda (catálogo curado, cache com validade, intervalo,
matriz Produto × Loja × Preço) e a ligação com o app. Usa as páginas reais salvas
em tests/fixtures/reais/ (sem acessar a internet)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lesteshop.app.pedido import ItemPedido, montar_pedido
from lesteshop.consulta import busca
from lesteshop.consulta import config as config_consulta
from lesteshop.consulta.cache import CacheConsulta
from lesteshop.consulta.catalogo import ItemCatalogo, carregar_catalogo_app
from lesteshop.data import config
from lesteshop.data.sources.http import ClienteHTTP, ErroColeta
from lesteshop.fiscal.categorias import carregar_categorias
from lesteshop.otimizacao.resolver import resolver
from lesteshop.otimizacao.solucao import descrever

from conftest import SessaoFalsa

REAIS = Path(__file__).parent / "fixtures" / "reais"
URL_MODELO = (REAIS / "modelo_url.txt").read_text().strip() if (REAIS / "modelo_url.txt").exists() else ""
pytestmark = pytest.mark.skipif(not URL_MODELO, reason="sem páginas reais em tests/fixtures/reais/")

PERFUME = ItemCatalogo("perfume", "Perfume La Vie Est Belle 100ml", "lancome la vie est belle 100ml",
                       "Perfumes", URL_MODELO)
PAGINA_SEM_DADOS = "<html><body><h1>Loja</h1></body></html>"  # loja sem endereço: fica de fora


class ClienteFalso:
    """Serve as páginas reais salvas; conta as requisições."""

    def __init__(self, extras: dict[str, str] | None = None, erro: Exception | None = None):
        self.paginas = {f"{config.URL_BASE_CP}/lojas/{f.stem[5:]}/": f.read_text(encoding="utf-8")
                        for f in REAIS.glob("loja_*.html")}
        self.paginas[URL_MODELO] = (REAIS / "modelo.html").read_text(encoding="utf-8")
        self.paginas.update(extras or {})
        self.erro = erro
        self.requisicoes = 0
        self.urls: list[str] = []
        self.fechado = False

    def get(self, url: str) -> str:
        if self.erro is not None:
            raise self.erro
        self.requisicoes += 1
        self.urls.append(url)
        return self.paginas.get(url, PAGINA_SEM_DADOS)

    def fechar(self):
        self.fechado = True


@pytest.fixture
def cache(tmp_path):
    return CacheConsulta(tmp_path / "consulta.db")


def _consultar(itens, cliente, cache, tmp_path):
    criados = []

    def criar():
        criados.append(cliente)
        return cliente

    res = busca.consultar(itens, criar, cache=cache, dir_cache_lojas=tmp_path / "lojas")
    return res, criados


# --- catálogo curado ----------------------------------------------------------
def test_catalogo_curado_valido():
    itens = carregar_catalogo_app()
    assert len(itens) >= 20
    assert len({i.id for i in itens}) == len(itens)
    categorias = carregar_categorias().por_categoria
    assert all(i.categoria in categorias for i in itens), "categoria fora de categorias_fiscais.csv"
    assert all(i.conteudo_por_unidade for i in itens if i.categoria == "Bebidas")


def test_catalogo_rejeita_id_repetido_e_url_que_nao_e_modelo(tmp_path):
    arq = tmp_path / "cat.json"
    arq.write_text(json.dumps({"produtos": [
        {"id": "a", "nome": "A", "termo": "a", "categoria": "Games"},
        {"id": "a", "nome": "B", "termo": "b", "categoria": "Games", "url_modelo": "https://x/lojas/y/"},
    ]}), encoding="utf-8")
    with pytest.raises(ValueError, match="id repetido.*url_modelo"):
        carregar_catalogo_app(arq)


# --- cache ------------------------------------------------------------------------
def test_cache_vale_seis_horas(tmp_path):
    relogio = [1000.0]
    c = CacheConsulta(tmp_path / "c.db", agora=lambda: relogio[0])
    c.gravar("x", {"ok": 1})
    relogio[0] += 6 * 3600 - 1
    assert c.obter("x") == {"ok": 1}
    relogio[0] += 2
    assert c.obter("x") is None


# --- consulta -----------------------------------------------------------------------
def test_consulta_monta_matriz_e_usa_cache_na_segunda_vez(cache, tmp_path):
    cli = ClienteFalso()
    res, criados = _consultar([PERFUME], cli, cache, tmp_path)
    assert criados and cli.fechado and res.requisicoes == cli.requisicoes > 0
    assert res.por_item["perfume"] == "CP-7965"
    m = res.matriz()
    assert len(m) == 10 and set(m.columns) == {"produto_id", "produto", "loja_id", "loja", "preco_usd"}
    assert m["preco_usd"].min() == 75.0 and "Intershop Importados" in set(m["loja"])
    assert set(res.ofertas["tipo_dado"]) == {"real"}
    assert res.lojas["latitude"].notna().all()

    # Segunda consulta dentro de 6 h: nenhum acesso ao site.
    res2, criados2 = _consultar([PERFUME], ClienteFalso(), cache, tmp_path)
    assert criados2 == [] and res2.do_cache == ["perfume"] and res2.requisicoes == 0
    assert res2.matriz().equals(m)


def test_item_sem_url_usa_a_busca_do_termo(cache, tmp_path):
    ps5 = "https://www.comprasparaguai.com.br/sony-playstation-5-pro-2tb-digital-edition_57629/"
    cli = ClienteFalso({f"{config.URL_BASE_CP}/busca/?q=playstation+5+pro": (REAIS / "busca.html").read_text(encoding="utf-8"),
                        ps5: (REAIS / "modelo.html").read_text(encoding="utf-8")})
    item = ItemCatalogo("ps5", "PS5 Pro", "playstation 5 pro", "Games")
    res, _ = _consultar([item], cli, cache, tmp_path)
    assert cli.urls[0].endswith("/busca/?q=playstation+5+pro") and cli.urls[1] == ps5
    assert res.por_item["ps5"] == "CP-57629"


def test_erro_de_acesso_interrompe_e_lista_os_itens_sem_consulta(cache, tmp_path):
    outro = ItemCatalogo("outro", "Outro", "outro", "Games")
    res, _ = _consultar([PERFUME, outro], ClienteFalso(erro=ErroColeta("verificação não resolvida.")), cache, tmp_path)
    assert res.nao_encontrados == ["perfume", "outro"] and res.por_item == {}
    assert "interrompida" in res.avisos[0]


def test_intervalo_entre_requisicoes(tmp_path):
    """O cliente da consulta espera ao menos INTERVALO_S entre acessos e não usa o
    cache diário de páginas (a validade é a do CacheConsulta)."""
    ClienteHTTP._ultimo_acesso.clear()
    esperas, relogio = [], [0.0]
    rotas = {f"{config.URL_BASE_CP}/robots.txt": "robots.txt",
             f"{config.URL_BASE_CP}/busca/?q=playstation+5+pro": "busca_playstation.html"}
    cli = ClienteHTTP(dir_cache=tmp_path, sessao=SessaoFalsa(rotas), intervalo=config_consulta.INTERVALO_S,
                      cache_paginas=False, dormir=lambda s: (esperas.append(s), relogio.__setitem__(0, relogio[0] + s)),
                      relogio=lambda: relogio[0])
    for _ in range(3):
        cli.get(f"{config.URL_BASE_CP}/busca/?q=playstation+5+pro")
    assert cli.requisicoes == 4  # robots.txt + 3 páginas (sem cache de página)
    assert esperas and all(e == pytest.approx(config_consulta.INTERVALO_S) for e in esperas)
    guardadas = list((tmp_path / "paginas" / cli.hoje.isoformat()).glob("*"))
    assert len(guardadas) == 1  # só o robots.txt


def test_consulta_alimenta_o_modelo_de_rota(cache, tmp_path):
    res, _ = _consultar([PERFUME], ClienteFalso(), cache, tmp_path)
    base = busca.para_base(res)
    assert base.origem == "real"
    inst = montar_pedido(base, [ItemPedido(res.por_item["perfume"], 1, 5)], "08:00", "15:00",
                         categorias=busca.mapa_categorias([PERFUME], res))
    sol, _ = resolver(inst)
    d = descrever(sol, inst)
    assert d["resumo"]["itens_comprados"] == 1
    assert d["roteiro"][0]["nome"] == "Intershop Importados"  # a mais barata (US$ 75)


def test_conteudo_das_bebidas_vem_do_catalogo(cache, tmp_path):
    res, _ = _consultar([PERFUME], ClienteFalso(), cache, tmp_path)
    whisky = ItemCatalogo("perfume", "Whisky 1L", "whisky", "Bebidas", URL_MODELO, 1.0)
    c = busca.mapa_categorias([whisky], res).classificar("CP-7965", "Bebidas")
    assert c.categoria_fiscal == "bebidas_alcoolicas" and c.conteudo_por_unidade == 1.0


# --- tela -------------------------------------------------------------------------
def test_tela_consulta_ao_vivo(cache, tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    from lesteshop.app import base as base_app

    original = busca.consultar
    monkeypatch.setattr(busca, "consultar", lambda itens, criar, progresso=None, dir_coletas=None: original(
        itens, criar, cache=cache, progresso=progresso, dir_cache_lojas=tmp_path / "lojas",
        dir_coletas=tmp_path / "coletas"))
    monkeypatch.setattr(busca, "criar_cliente_navegador", ClienteFalso)
    monkeypatch.setattr(base_app, "cotacao_para_exibir", lambda *a, **k: None)
    monkeypatch.setattr("lesteshop.app.tela.carregar_catalogo_app", lambda: [PERFUME])
    from lesteshop.app import tela
    tela._catalogo.clear()  # o Streamlit guarda o catálogo entre execuções
    raiz = Path(__file__).resolve().parents[1]
    at = AppTest.from_file(str(raiz / "app.py"), default_timeout=120)
    at.run()
    assert not at.exception
    at.text_input(key="busca_produto").input("belle vie perfume").run()  # qualquer ordem
    next(b for b in at.button if b.key == "add_perfume").click().run()
    next(b for b in at.button if b.label == "Calcular roteiro").click().run()
    assert not at.exception
    assert any("Preços do Compras Paraguai, consultados em" in s.value for s in at.success)
    textos = " ".join(m.value for m in at.markdown)
    assert "Roteiro" in textos
    assert list((tmp_path / "coletas").glob("*/ofertas.csv")), "a consulta deve entrar na base"
    tela._catalogo.clear()



def test_buscar_no_site_usa_cache(cache):
    cli = ClienteFalso({f"{config.URL_BASE_CP}/busca/?q=playstation+5+pro":
                        (REAIS / "busca.html").read_text(encoding="utf-8")})
    modelos = busca.buscar_no_site("playstation 5 pro", lambda: cli, cache=cache)
    assert modelos[0]["nome"] == "Sony Playstation 5 Pro 2TB Digital Edition" and cli.fechado
    assert busca.buscar_no_site("Playstation 5 PRO", lambda: pytest.fail("deveria usar o cache"),
                                cache=cache) == modelos


def test_item_consultado_entra_na_base_guardada(cache, tmp_path):
    res = busca.consultar([PERFUME], lambda: ClienteFalso(), cache=cache,
                          dir_cache_lojas=tmp_path / "lojas", dir_coletas=tmp_path / "coletas")
    pasta = next((tmp_path / "coletas").iterdir())
    from lesteshop.data.sources.fonte_csv import FonteCSV
    guardado = FonteCSV(pasta)
    assert set(guardado.carregar_produtos()["produto_id"]) == {"CP-7965"}
    assert len(guardado.carregar_ofertas()) == len(res.ofertas) and len(guardado.carregar_lojas()) == 10
    # Vindo do cache, não grava de novo (nem duplica).
    busca.consultar([PERFUME], lambda: pytest.fail("deveria usar o cache"), cache=cache,
                    dir_coletas=tmp_path / "coletas")
    assert len(FonteCSV(pasta).carregar_ofertas()) == len(res.ofertas)


def test_tela_produto_fora_da_base_e_procurado_no_site(monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    from lesteshop.app import base as base_app
    from lesteshop.app import tela

    monkeypatch.setattr(base_app, "cotacao_para_exibir", lambda *a, **k: None)
    monkeypatch.setattr(busca, "buscar_no_site", lambda texto, criar: [
        {"nome": "Antena Starlink Mini Kit", "url": "https://www.comprasparaguai.com.br/antena-starlink-mini_61234/",
         "modelo_id": "61234"}])
    tela._catalogo.clear()
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    at.run()
    at.text_input(key="busca_produto").input("antena zzzz").run()   # não está na base
    assert any("Encontrados no Compras Paraguai" in c.value for c in at.caption)
    next(b for b in at.button if b.key == "add_cp:61234").click().run()
    assert not at.exception and at.session_state["lista"] == ["cp:61234"]
