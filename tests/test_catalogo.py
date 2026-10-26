import datetime as dt
import time

import pandas as pd
import pytest

from lesteshop.data import catalogo
from lesteshop.data.catalogo import ErroCatalogo


@pytest.fixture
def csv_catalogo(tmp_path):
    df = pd.DataFrame([
        ("CP-1", "Sony Playstation 5 Pro 2TB Digital Edition", "u1"),
        ("CP-2", "Sony Playstation 5 Slim 1TB", "u2"),
        ("CP-3", "Controle Sony DualSense Edge PS5", "u3"),
        ("CP-4", "Perfume Lancôme La Vie Est Belle EDP 100ml", "u4"),
        ("CP-5", "Câmera GoPro Hero 12 Black", "u5"),
        ("CP-6", "Smartphone Xiaomi Redmi Note 13 Pro 256GB", "u6"),
    ], columns=["modelo_id", "nome", "url"])
    df["categoria"] = None
    df["data_atualizacao"] = "2026-10-01"
    caminho = tmp_path / "catalogo.csv"
    df.to_csv(caminho, index=False)
    return caminho


def test_sugerir_palavras_fora_de_ordem(csv_catalogo):
    r = catalogo.sugerir_modelos("playstation 5 pro", caminho=csv_catalogo)
    assert r.iloc[0]["nome"] == "Sony Playstation 5 Pro 2TB Digital Edition"
    assert len(r) == 1
    r = catalogo.sugerir_modelos("pro digital PLAYSTATION", caminho=csv_catalogo)
    assert r.iloc[0]["modelo_id"] == "CP-1"


def test_sugerir_ignora_acentos(csv_catalogo):
    assert catalogo.sugerir_modelos("camera gopro", caminho=csv_catalogo).iloc[0]["modelo_id"] == "CP-5"
    assert catalogo.sugerir_modelos("LANCOME vie", caminho=csv_catalogo).iloc[0]["modelo_id"] == "CP-4"
    assert catalogo.sugerir_modelos("câméra", caminho=csv_catalogo).iloc[0]["modelo_id"] == "CP-5"


def test_sugerir_por_prefixo_e_limite(csv_catalogo):
    r = catalogo.sugerir_modelos("play", caminho=csv_catalogo)
    assert set(r["modelo_id"]) == {"CP-1", "CP-2"}
    assert len(catalogo.sugerir_modelos("sony", limite=2, caminho=csv_catalogo)) == 2
    assert catalogo.sugerir_modelos("inexistente", caminho=csv_catalogo).empty
    assert catalogo.sugerir_modelos("   ", caminho=csv_catalogo).empty


def test_sugerir_responde_em_menos_de_100ms(tmp_path):
    marcas = ["Sony", "Apple", "Samsung", "Xiaomi", "Lenovo", "Dell", "JBL", "Nike", "Dior", "Canon"]
    tipos = ["Playstation", "iPhone", "Galaxy", "Redmi", "Notebook", "Monitor", "Caixa", "Tênis", "Perfume", "Câmera"]
    linhas = [(f"CP-{i}", f"{marcas[i % 10]} {tipos[(i // 10) % 10]} {i % 7} Pro {i}GB Edição {i % 13}", f"u{i}")
              for i in range(60000)]
    df = pd.DataFrame(linhas, columns=["modelo_id", "nome", "url"]).assign(categoria=None, data_atualizacao="2026-10-01")
    caminho = tmp_path / "grande.csv"
    df.to_csv(caminho, index=False)
    catalogo.sugerir_modelos("sony", caminho=caminho)  # monta e aquece o índice (uma vez)
    for consulta in ("playstation 5 pro", "sony", "p", "camera canon edicao 3"):
        tempos = []
        for _ in range(3):  # melhor de 3: ignora oscilações da máquina (ex.: CI compartilhado)
            ini = time.perf_counter()
            catalogo.sugerir_modelos(consulta, caminho=caminho)
            tempos.append(time.perf_counter() - ini)
        assert min(tempos) < 0.1, (consulta, tempos)


def test_extrai_somente_urls_de_modelo_do_sitemap(cliente_falso):
    df = catalogo.coletar_catalogo(cliente_falso)
    assert sorted(df["modelo_id"]) == ["CP-51234", "CP-51888", "CP-60001", "CP-70100"]
    nomes = dict(zip(df["modelo_id"], df["nome"]))
    assert nomes["CP-51234"] == "Sony Playstation 5 Pro 2TB Digital Edition"
    assert nomes["CP-70100"] == "Perfume Acqua Di Gio EDT 100ML" or "Acqua" in nomes["CP-70100"]


def test_atualizar_catalogo_grava_csv_e_meta(cliente_falso, tmp_path):
    csv, meta = tmp_path / "cat.csv", tmp_path / "meta.json"
    pd.DataFrame([("CP-1", "Modelo Antigo", "https://x/antigo_1/", None, "2026-01-01"),
                  ("CP-51234", "Sony Playstation 5 Pro 2TB Digital Edition",
                   "https://www.comprasparaguai.com.br/sony-playstation-5-pro-2tb-digital-edition_51234/", None, "2026-09-01")],
                 columns=["modelo_id", "nome", "url", "categoria", "data_atualizacao"]).to_csv(csv, index=False)
    info = catalogo.atualizar_catalogo(csv, meta, cliente=cliente_falso, hoje=dt.date(2026, 10, 19))
    assert (info["novos"], info["removidos"], info["total"]) == (3, 1, 4)
    df = catalogo.carregar_catalogo(csv)
    datas = dict(zip(df["modelo_id"], df["data_atualizacao"]))
    assert datas["CP-51234"] == "2026-09-01"   # inalterado mantém a data
    assert datas["CP-60001"] == "2026-10-19"   # novo recebe a data da atualização
    assert '"ultima_atualizacao": "2026-10-19"' in meta.read_text()


def test_falha_na_coleta_nao_sobrescreve_catalogo(cliente_falso, tmp_path):
    csv = tmp_path / "cat.csv"
    csv.write_text("modelo_id,nome,url,categoria,data_atualizacao\nCP-1,X,u,,2026-01-01\n")
    antes = csv.read_bytes()
    cliente_falso.sessao_falsa.rotas.pop("https://www.comprasparaguai.com.br/sitemap.xml")
    with pytest.raises(ErroCatalogo, match="Falha ao baixar o sitemap"):
        catalogo.atualizar_catalogo(csv, tmp_path / "m.json", cliente=cliente_falso)
    assert csv.read_bytes() == antes and not (tmp_path / "m.json").exists()


def test_sitemap_sem_modelos_nao_sobrescreve(cliente_falso, tmp_path):
    csv = tmp_path / "cat.csv"
    csv.write_text("modelo_id,nome,url,categoria,data_atualizacao\nCP-1,X,u,,2026-01-01\n")
    cliente_falso.sessao_falsa.rotas["https://www.comprasparaguai.com.br/sitemap.xml"] = "sitemap_lojas.xml"
    with pytest.raises(ErroCatalogo, match="nenhuma URL de modelo"):
        catalogo.atualizar_catalogo(csv, tmp_path / "m.json", cliente=cliente_falso)
    assert "CP-1" in csv.read_text()


def test_sitemap_xml_invalido():
    with pytest.raises(ErroCatalogo, match="não é um XML válido"):
        catalogo.ler_sitemap(b"<html>manutencao")
