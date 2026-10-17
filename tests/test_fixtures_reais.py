"""Confere o parser contra páginas reais salvas com
``python -m lesteshop.data.salvar_fixtures``. Pulado se não houver páginas."""

from pathlib import Path

import pytest

from lesteshop.data.sources import parser_cp

REAIS = Path(__file__).parent / "fixtures" / "reais"
pytestmark = pytest.mark.skipif(not (REAIS / "modelo.html").exists(),
                                reason="sem páginas reais em tests/fixtures/reais/")


def test_busca_real_tem_modelos():
    modelos = parser_cp.parse_busca((REAIS / "busca.html").read_text(encoding="utf-8"))
    assert modelos and all(m["nome"] and m["url"] for m in modelos)


def test_modelo_real_tem_ofertas_com_preco():
    url = (REAIS / "modelo_url.txt").read_text().strip()
    modelo = parser_cp.parse_modelo((REAIS / "modelo.html").read_text(encoding="utf-8"), url)
    assert modelo["ofertas"]
    assert all(o["preco_usd"] > 0 and o["loja_slug"] for o in modelo["ofertas"])


@pytest.mark.parametrize("arquivo", sorted(REAIS.glob("loja_*.html")) if REAIS.exists() else [])
def test_loja_real_tem_nome(arquivo):
    loja = parser_cp.parse_loja(arquivo.read_text(encoding="utf-8"), arquivo.stem[5:])
    assert loja["nome"]
