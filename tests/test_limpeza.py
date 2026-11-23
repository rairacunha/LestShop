"""Limpeza antes de gravar, lista inicial de lojas e consulta dos últimos 7 dias (23/11/2026)."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from lesteshop.data import database, esquema, limpeza


def _lojas(*linhas):
    return esquema.padronizar(pd.DataFrame([dict(
        loja_id=i, nome=n, slug=i, cidade="Ciudad del Este", endereco=None, predio=pr,
        latitude=la, longitude=lo, coordenada_pendente=la is None, abre="07:00", fecha="16:00",
        tempo_permanencia_min=20, fonte="teste", tipo_dado="real") for i, n, pr, la, lo in linhas]), "lojas")


def _produtos(*linhas):
    return esquema.padronizar(pd.DataFrame([dict(produto_id=i, nome=n, categoria="Games",
                                                 url_modelo=f"https://x/{i}", tipo_dado="real")
                                            for i, n in linhas]), "produtos")


def _ofertas(*linhas, data="2026-11-20"):
    return esquema.padronizar(pd.DataFrame([dict(loja_id=l, produto_id=p, titulo_oferta=t, preco_usd=v,
                                                 data_coleta=data, fonte="teste", tipo_dado="real")
                                            for l, p, t, v in linhas]), "ofertas")


@pytest.mark.parametrize("nome, chave", [
    ("Shopping China Importados", "shoppingchina"), ("Visão VIP", "visaovip"), ("Visãovip", "visaovip"),
    ("Cell Shop", "cellshop"), ("Mega Eletrônicos", "megaeletronicos"), ("Mega Eletro", "megaeletro"),
])
def test_chave_da_loja(nome, chave):
    assert limpeza.chave_loja(nome) == chave


def test_slug_do_produto():
    assert limpeza.slug_produto("Controle Sony DualSense — PlayStation 5") == "controle-sony-dualsense-playstation-5"


@pytest.mark.parametrize("titulo, produto, motivo", [
    ("iPhone 16 128GB Vitrine", "Apple iPhone 16 128GB", "condição: vitrine"),
    ("Apple iPhone 16 CPO 128GB", "Apple iPhone 16 128GB", "condição: cpo"),
    ("iPhone 16 Reacondicionado", "Apple iPhone 16 128GB", "condição: reacondicionado"),
    ("Capa para iPhone 16", "Apple iPhone 16 128GB", "acessório: capa"),
    ("Película de vidro iPhone 16", "Apple iPhone 16 128GB", "acessório: pelicula"),
    ("Controle sem fio Xbox cabo USB-C", "Controle Microsoft Xbox", None),   # cabo no meio: fica
    ("Carregador Apple 20W USB-C", "Carregador Apple 20W", None),            # o produto é o carregador
    ("Apple iPhone 16 A3287 128 GB - Teal", "Apple iPhone 16 128GB", None),
])
def test_filtro_de_ofertas(titulo, produto, motivo):
    assert limpeza.motivo_descarte(titulo, produto, limpeza.carregar_filtro()) == motivo


def test_preparar_une_duplicatas_e_usa_a_lista_inicial():
    lojas = _lojas(("CP-shopping-china", "Shopping China", "Shopping China", -25.515006, -54.606187),
                   ("CP-shopping-china-importados", "Shopping China Importados", None, -25.51505, -54.60620),
                   ("CP-nissei", "Nissei", "Galería Hijazi Center", -25.511024, -54.609604),
                   ("CP-nissei-km7", "Casa Nissei", None, -25.5160, -54.6450),   # filial a 4 km: fica separada
                   ("CP-pioneer", "Pioneer", None, None, None))                    # sem coordenada no site
    produtos = _produtos(("P1", "PS5 Pro"), ("P2", "PS5  PRO"), ("P3", "Mouse"))
    ofertas = _ofertas(("CP-shopping-china", "P1", "PS5 Pro", 700), ("CP-shopping-china-importados", "P2", "PS5 Pro", 690),
                       ("CP-nissei", "P1", "PS5 Pro Vitrine", 500), ("CP-nissei-km7", "P3", "Capa para mouse", 5),
                       ("CP-pioneer", "P3", "Mouse", 30))
    r = limpeza.preparar(lojas, produtos, ofertas)
    assert list(r.produtos["produto_id"]) == ["P1", "P3"]                      # P2 = mesmo slug de P1
    assert r.produtos["slug"].is_unique
    ids = set(r.lojas["loja_id"])
    assert "CP-shopping-china-importados" not in ids and {"CP-nissei", "CP-nissei-km7"} <= ids
    assert set(r.ofertas["loja_id"]) <= ids and set(r.ofertas["produto_id"]) <= {"P1", "P3"}
    assert len(r.ofertas) == 3 and sorted(r.descartes["motivo"]) == ["acessório: capa", "condição: vitrine"]
    l = r.lojas.set_index("loja_id")
    assert l.at["CP-nissei-km7", "nome"] == "Nissei" and l.at["CP-nissei-km7", "zona"] == "Fora do centro"
    pio = l.loc["CP-pioneer"]   # coordenada estimada da lista inicial, só porque o site não tinha
    assert pio["nome"] == "Pioneer Internacional" and pio["latitude"] == pytest.approx(-25.51)
    assert not pio["coordenada_pendente"] and any("lista inicial" in a for a in r.avisos)
    assert r.ofertas["url_oferta"].notna().all() and (r.ofertas["coletado_em"] == "2026-11-20").all()


def test_coordenada_do_site_vale_mais_que_a_lista_inicial():
    lojas = _lojas(("CP-cellshop", "Cell Shop", None, -25.5111, -54.6111))
    r = limpeza.preparar(lojas, _produtos(("P1", "X")), _ofertas(("CP-cellshop", "P1", "X", 10)))
    l = r.lojas.iloc[0]
    assert (l["latitude"], l["predio"], l["nome"]) == (-25.5111, "Shopping Ibiza", "Cellshop")


def test_lista_inicial_tem_as_nove_lojas():
    seed, apelidos = limpeza.carregar_seed()
    nomes = {s.nome for s in seed.values()}
    assert nomes == {"Cellshop", "Nissei", "Mega Eletrônicos", "Shopping China", "Monalisa", "Madrid Center",
                     "Atacado Games", "Visão VIP", "Pioneer Internacional"}
    estimadas = {s.nome for s in seed.values() if s.origem_coordenada.startswith("ESTIMADA")}
    assert estimadas == {"Monalisa", "Atacado Games", "Pioneer Internacional"}
    assert apelidos["casanissei"] == "nissei"


def test_gravar_limpa_e_consulta_ultimos_7_dias(tmp_path):
    con = database.conectar(tmp_path / "b.db")
    lojas = _lojas(("CP-a", "Loja A", None, -25.51, -54.61), ("CP-b", "Loja B", None, -25.512, -54.608))
    produtos = _produtos(("P1", "PS5 Pro"))
    database.gravar(con, lojas, produtos, _ofertas(("CP-a", "P1", "PS5 Pro", 700), ("CP-a", "P1", "PS5 Pro azul", 690),
                                                   ("CP-b", "P1", "PS5 Pro CPO", 400), data="2026-11-20"))
    database.gravar(con, lojas, produtos, _ofertas(("CP-b", "P1", "PS5 Pro", 650), data="2026-11-01"))
    assert con.execute("SELECT motivo FROM descartes_coleta").fetchall() == [("condição: cpo",)]
    v = database.ofertas_validas(con, hoje=dt.date(2026, 11, 23))
    assert list(zip(v["loja_id"], v["menor_preco_usd"], v["n_ofertas"])) == [("CP-a", 690.0, 2)]  # CP-b: antiga
    assert v.iloc[0]["url_oferta"] == "https://x/P1" and v.iloc[0]["zona"] == "Microcentro"
    assert len(database.ofertas_validas(con, dias=30, hoje=dt.date(2026, 11, 23))) == 2
    # Outra coleta com outro id e o mesmo nome não duplica o produto.
    database.gravar(con, lojas, _produtos(("P9", "PS5 PRO")), _ofertas(("CP-a", "P9", "PS5 Pro", 680), data="2026-11-22"))
    assert con.execute("SELECT COUNT(*) FROM produtos").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM ofertas WHERE produto_id='P1'").fetchone()[0] == 4


def test_banco_antigo_ganha_as_colunas_novas(tmp_path):
    import sqlite3

    caminho = tmp_path / "velho.db"
    velho = sqlite3.connect(caminho)
    velho.execute("CREATE TABLE produtos (produto_id TEXT PRIMARY KEY, nome TEXT NOT NULL, categoria TEXT, "
                  "url_modelo TEXT, peso_kg REAL, volume_l REAL, desconto_brasil_pct REAL, tipo_dado TEXT NOT NULL)")
    velho.execute("INSERT INTO produtos VALUES ('P1','X',NULL,NULL,NULL,NULL,NULL,'real')")
    velho.commit()
    velho.close()
    con = database.conectar(caminho)
    assert "slug" in {r[1] for r in con.execute("PRAGMA table_info(produtos)")}
    assert con.execute("SELECT nome FROM produtos").fetchone() == ("X",)
