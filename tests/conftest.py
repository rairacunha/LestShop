from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from lesteshop.data import config
from lesteshop.data.sources.fonte_csv import FonteCSV

FIXTURES = Path(__file__).parent / "fixtures"
URL = config.URL_BASE_CP


class RespostaFalsa:
    def __init__(self, status_code: int, conteudo: bytes):
        self.status_code = status_code
        self.content = conteudo
        self.text = conteudo.decode("utf-8")


class SessaoFalsa:
    """Imita requests.Session.get servindo arquivos de tests/fixtures/."""

    def __init__(self, rotas: dict[str, str]):
        self.rotas = dict(rotas)
        self.acessos: list[str] = []
        self.headers_usados: list[dict] = []

    def get(self, url, headers=None, timeout=None):
        self.acessos.append(url)
        self.headers_usados.append(headers or {})
        if url not in self.rotas:
            return RespostaFalsa(404, b"nao encontrado")
        return RespostaFalsa(200, (FIXTURES / self.rotas[url]).read_bytes())


ROTAS_CP = {
    f"{URL}/robots.txt": "robots.txt",
    f"{URL}/busca/?q=playstation+5+pro": "busca_playstation.html",
    f"{URL}/sony-playstation-5-pro-2tb-digital-edition_51234/": "modelo_ps5pro.html",
    f"{URL}/lojas/eletro-leste/": "loja_eletro-leste.html",
    f"{URL}/lojas/games-del-este/": "loja_games-del-este.html",
    f"{URL}/lojas/importados-ponte/": "loja_importados-ponte.html",
    f"{URL}/lojas/guaira-tech/": "loja_guaira-tech.html",
    f"{URL}/sitemap.xml": "sitemap_index.xml",
    f"{URL}/sitemap-produtos-1.xml": "sitemap_produtos_1.xml",
    f"{URL}/sitemap-lojas.xml": "sitemap_lojas.xml",
}


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def ler_fixture():
    return lambda nome: (FIXTURES / nome).read_text(encoding="utf-8")


@pytest.fixture
def cliente_falso(tmp_path):
    from lesteshop.data.sources.http import ClienteHTTP

    ClienteHTTP._ultimo_acesso.clear()
    sessao = SessaoFalsa(ROTAS_CP)
    esperas: list[float] = []
    relogio = [0.0]
    cliente = ClienteHTTP(
        dir_cache=tmp_path / "cache", sessao=sessao,
        dormir=lambda s: (esperas.append(s), relogio.__setitem__(0, relogio[0] + s)),
        relogio=lambda: relogio[0], hoje=dt.date(2026, 10, 17),
    )
    cliente.sessao_falsa = sessao
    cliente.esperas = esperas
    return cliente


SEMENTE = FIXTURES / "semente"  # base pequena e estável usada pelos testes


@pytest.fixture
def semente():
    fonte = FonteCSV(SEMENTE)
    base = fonte.carregar_tudo()
    base["pontos_partida"] = fonte.carregar_pontos_partida()
    return base
