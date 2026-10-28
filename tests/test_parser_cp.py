import pytest

from lesteshop.data.sources import parser_cp
from lesteshop.data.sources.parser_cp import ErroEstruturaHTML

URL_MODELO = "https://www.comprasparaguai.com.br/sony-playstation-5-pro-2tb-digital-edition_51234/"


def test_busca_extrai_modelos_nome_url_e_preco(ler_fixture):
    modelos = parser_cp.parse_busca(ler_fixture("busca_playstation.html"))
    assert [m["modelo_id"] for m in modelos] == ["51234", "51888", "40017"]
    ps5 = modelos[0]
    assert ps5["nome"] == "Sony Playstation 5 Pro 2TB Digital Edition"
    assert ps5["url"] == URL_MODELO
    assert ps5["preco_a_partir_usd"] == 689.00
    assert modelos[2]["preco_a_partir_usd"] == 185.50


def test_busca_sem_resultados_devolve_lista_vazia(ler_fixture):
    assert parser_cp.parse_busca(ler_fixture("busca_sem_resultados.html")) == []


def test_busca_com_html_desconhecido_gera_erro_claro():
    with pytest.raises(ErroEstruturaHTML, match="HTML do site provavelmente mudou"):
        parser_cp.parse_busca("<html><body><main><div>layout novo</div></main></body></html>")


def test_modelo_extrai_ofertas(ler_fixture):
    modelo = parser_cp.parse_modelo(ler_fixture("modelo_ps5pro.html"), URL_MODELO)
    assert modelo["nome"] == "Sony Playstation 5 Pro 2TB Digital Edition"
    assert modelo["categoria"] == "Consoles"
    ofertas = {o["loja_slug"]: o for o in modelo["ofertas"]}
    # a barra lateral "Lojas parceiras" (sem preço) não vira oferta nem duplica
    assert len(modelo["ofertas"]) == 5
    assert set(ofertas) == {"eletro-leste", "games-del-este", "importados-ponte", "guaira-tech", "pjc-games"}
    el = ofertas["eletro-leste"]
    assert el["preco_usd"] == 689.00
    assert el["preco_brl"] == 3769.83
    assert el["codigo_loja"] == "778812"
    assert el["titulo_oferta"] == "Console Sony PlayStation 5 Pro 2TB Digital - CFI-7021B"
    assert el["cidade"] == "Ciudad del Este"
    assert ofertas["games-del-este"]["codigo_loja"] == "GDE-5521"
    assert ofertas["importados-ponte"]["preco_usd"] == 1049.90
    assert ofertas["importados-ponte"]["preco_brl"] is None
    assert ofertas["pjc-games"]["cidade"] == "Pedro Juan Caballero"


def test_modelo_converte_peso_bruto_e_dimensoes_da_embalagem(ler_fixture):
    modelo = parser_cp.parse_modelo(ler_fixture("modelo_ps5pro.html"), URL_MODELO)
    assert modelo["peso_kg"] == 4.6          # "Peso Bruto", não o líquido
    assert modelo["volume_l"] == pytest.approx(26.79)  # 47 x 38 x 15 cm da embalagem


def test_modelo_sem_especificacoes_nao_inventa_peso():
    html = """<main><h1>Produto X</h1><div class='o'><a href='/lojas/a/'>A</a> US$ 10,00</div></main>"""
    modelo = parser_cp.parse_modelo(html, "u")
    assert modelo["peso_kg"] is None and modelo["volume_l"] is None


@pytest.mark.parametrize("texto,esperado", [
    ("4,6 kg", 4.6), ("850 g", 0.85), ("2 lb", 0.9072), ("sem dado", None), (None, None)])
def test_converter_peso(texto, esperado):
    assert parser_cp.converter_peso_kg(texto) == esperado


@pytest.mark.parametrize("texto,esperado", [
    ("47 x 38 x 15 cm", 26.79), ("100 x 200 x 50 mm", 1.0), ("47 x 38 cm", None)])
def test_converter_volume(texto, esperado):
    assert parser_cp.converter_volume_l(texto) == esperado


def test_modelo_com_layout_novo_gera_erro_em_vez_de_dados_vazios(ler_fixture):
    with pytest.raises(ErroEstruturaHTML, match="Nenhuma oferta encontrada"):
        parser_cp.parse_modelo(ler_fixture("modelo_quebrado.html"), URL_MODELO)


def test_modelo_sem_h1_gera_erro():
    with pytest.raises(ErroEstruturaHTML, match="sem título"):
        parser_cp.parse_modelo("<html><body><p>oi</p></body></html>", URL_MODELO)


def test_loja_com_mapa_do_google(ler_fixture):
    loja = parser_cp.parse_loja(ler_fixture("loja_eletro-leste.html"), "eletro-leste")
    assert loja["nome"] == "Eletro Leste"
    assert loja["cidade"] == "Ciudad del Este"
    assert loja["endereco"].startswith("Av. Monseñor Rodríguez, Shopping Exemplo Paraná")
    assert (loja["latitude"], loja["longitude"]) == (-25.51094, -54.60975)
    assert (loja["abre"], loja["fecha"]) == ("07:00", "16:30")


def test_loja_sem_mapa_fica_sem_coordenadas(ler_fixture):
    loja = parser_cp.parse_loja(ler_fixture("loja_games-del-este.html"), "games-del-este")
    assert loja["cidade"] == "Ciudad del Este"
    assert "Galería Exemplo Central" in loja["endereco"]
    assert loja["latitude"] is None and loja["longitude"] is None


def test_loja_com_json_ld(ler_fixture):
    loja = parser_cp.parse_loja(ler_fixture("loja_importados-ponte.html"), "importados-ponte")
    assert loja["cidade"] == "Ciudad del Este"
    assert (loja["latitude"], loja["longitude"]) == (-25.5148, -54.6121)


def test_loja_de_outra_cidade(ler_fixture):
    loja = parser_cp.parse_loja(ler_fixture("loja_guaira-tech.html"), "guaira-tech")
    assert loja["cidade"] == "Salto del Guairá"


def test_loja_sem_h1_gera_erro():
    with pytest.raises(ErroEstruturaHTML):
        parser_cp.parse_loja("<html><body></body></html>", "x")


def test_modelo_extrai_desconto_em_relacao_ao_brasil(ler_fixture):
    modelo = parser_cp.parse_modelo(ler_fixture("modelo_ps5pro.html"), URL_MODELO)
    assert modelo["desconto_brasil_pct"] == 0.28


def test_modelo_sem_aviso_de_desconto_fica_vazio():
    html = """<main><h1>Produto X</h1><div class='o'><a href='/lojas/a/'>A</a> US$ 10,00</div></main>"""
    assert parser_cp.parse_modelo(html, "u")["desconto_brasil_pct"] is None


@pytest.mark.parametrize("texto,esperado", [
    ("~28% mais barato que no Brasil", 0.28),
    ("Até 31,5 % mais barato do que no Brasil", 0.315),
    ("Economize no Paraguai", None),
    ("150% mais barato que no Brasil", None),
])
def test_extrair_desconto_brasil(texto, esperado):
    assert parser_cp.extrair_desconto_brasil(texto) == esperado
