"""A base fictícia (data/raw) e as instâncias de data/instances são válidas."""

import datetime as dt
import json

import pandas as pd
import pytest

from lesteshop.data import config
from lesteshop.data.sources.fonte_csv import FonteCSV
from lesteshop.data.validator import validar

HOJE = dt.date(2026, 10, 26)
INSTANCIAS = sorted(p for p in config.DIR_INSTANCIAS.glob("inst_*") if p.is_dir())


def test_base_ficticia_valida_e_marcada_como_sintetica():
    t = FonteCSV(config.DIR_RAW).carregar_tudo()
    r = validar(t["lojas"], t["produtos"], t["ofertas"], hoje=HOJE)
    assert r.ok, r.erros
    assert (len(r.lojas), len(r.produtos), len(r.ofertas)) == (50, 73, 613)
    for df in (t["lojas"], t["produtos"], t["ofertas"]):
        assert (df["tipo_dado"] == "sintetico").all()
    # todo produto tem escolha de loja (essência do TPP)
    assert t["ofertas"].groupby("produto_id")["loja_id"].nunique().min() >= 2


def test_cem_instancias():
    assert len(INSTANCIAS) == 100
    tamanhos = pd.Series([json.loads((p / "metadata.json").read_text())["tamanho"] for p in INSTANCIAS])
    assert tamanhos.value_counts().to_dict() == {"pequena": 40, "media": 35, "grande": 25}


@pytest.mark.parametrize("pasta", INSTANCIAS, ids=lambda p: p.name)
def test_instancia_valida(pasta):
    t = FonteCSV(pasta).carregar_tudo()
    r = validar(t["lojas"], t["produtos"], t["ofertas"], hoje=HOJE)
    assert r.ok, r.erros
    lista = pd.read_csv(pasta / "lista_compras.csv", dtype={"produto_id": str})
    assert set(lista["produto_id"]) <= set(t["produtos"]["produto_id"])
    meta = json.loads((pasta / "metadata.json").read_text())
    assert meta["n_ofertas"] == len(t["ofertas"]) and meta["tipo_dado"] == "sintetico"
