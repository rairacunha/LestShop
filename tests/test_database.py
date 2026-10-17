import pytest

from lesteshop.data import database
from lesteshop.data.sources import FonteAPI, FonteComprasParaguai, FonteCSV


@pytest.fixture
def con(tmp_path):
    return database.recriar_banco(tmp_path / "t.db", fontes=[FonteCSV()])


def test_recriar_banco_com_chaves(con):
    assert con.execute("SELECT COUNT(*) FROM lojas").fetchone()[0] == 8
    assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    fks = con.execute("PRAGMA foreign_key_list(ofertas)").fetchall()
    assert {f[2] for f in fks} == {"lojas", "produtos"}
    assert con.execute("SELECT nome FROM pontos_partida WHERE id = 0").fetchone()[0].startswith("Ponte da Amizade")
    with pytest.raises(Exception):
        con.execute("INSERT INTO ofertas (loja_id, produto_id, preco_usd, data_coleta, fonte, tipo_dado) "
                    "VALUES ('X', 'P01', 10, '2026-10-17', 'f', 'real')")


def test_lojas_que_vendem_ordena_pelo_menor_preco(con):
    df = database.lojas_que_vendem("playstation 5 pro", con)
    assert len(df) >= 2
    assert df["preco_usd"].is_monotonic_increasing
    assert set(df["produto"]) == {"Sony PlayStation 5 Pro 2TB Digital Edition"}
    assert {"loja", "preco_usd", "data_coleta"} <= set(df.columns)


def test_lojas_que_vendem_sem_acento_e_fora_de_ordem(con):
    assert len(database.lojas_que_vendem("camera gopro", con)) > 0
    assert len(database.lojas_que_vendem("pro playstation", con)) > 0
    assert database.lojas_que_vendem("produto inexistente", con).empty


def test_gravar_coleta_real_no_banco(con, cliente_falso, tmp_path):
    import datetime as dt
    fonte = FonteComprasParaguai(termos=["playstation 5 pro"], cliente=cliente_falso,
                                 dir_cache_lojas=tmp_path / "lojas", hoje=dt.date(2026, 10, 17))
    res = fonte.coletar()
    database.gravar(con, res.lojas, res.produtos, res.ofertas, res.descartes)
    database.gravar(con, res.lojas, res.produtos, res.ofertas)  # regravar não duplica
    assert con.execute("SELECT COUNT(*) FROM ofertas WHERE fonte='comprasparaguai.com.br'").fetchone()[0] == 3
    df = database.lojas_que_vendem("playstation 5 pro 2tb digital edition", con)
    assert df.iloc[0]["preco_usd"] == 689.0 and df.iloc[0]["tipo_dado"] == "real"
    assert con.execute("SELECT COUNT(*) FROM descartes_coleta").fetchone()[0] == 2


def test_complemento_manual_de_coordenadas(semente, tmp_path):
    comp = tmp_path / "comp.csv"
    comp.write_text("loja_id,latitude,longitude,predio,observacao\nS08,-25.5120,-54.6100,Galería X,Google Maps\n")
    lojas = database.aplicar_complemento_lojas(semente["lojas"], comp)
    s08 = lojas.set_index("loja_id").loc["S08"]
    assert not s08["coordenada_pendente"] and s08["predio"] == "Galería X"


def test_fonte_api_e_apenas_esqueleto():
    with pytest.raises(NotImplementedError):
        FonteAPI().carregar_ofertas()
