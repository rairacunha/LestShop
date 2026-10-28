import json

import pandas as pd
import pytest

from lesteshop.data import generator
from lesteshop.data.validator import validar


@pytest.fixture(scope="module")
def base_ficticia():
    return generator.carregar_base("semente")  # data/raw: 50 lojas, 73 produtos


@pytest.mark.parametrize("tamanho,n_lojas,n_produtos", [("pequena", 5, 10), ("media", 15, 40), ("grande", 40, 70)])
def test_tamanhos_e_validade(base_ficticia, tamanho, n_lojas, n_produtos):
    inst = generator.gerar_instancia(tamanho, seed=1, base=base_ficticia)
    assert len(inst["lojas"]) == n_lojas and len(inst["produtos"]) == n_produtos
    res = validar(inst["lojas"], inst["produtos"], inst["ofertas"])
    assert res.ok, res.erros
    assert (inst["ofertas"]["tipo_dado"] == "sintetico").all()
    assert not inst["lojas"]["coordenada_pendente"].any()


def test_mesma_seed_gera_a_mesma_instancia(base_ficticia):
    a = generator.gerar_instancia("media", seed=42, base=base_ficticia)
    b = generator.gerar_instancia("media", seed=42, base=base_ficticia)
    for t in ("lojas", "produtos", "ofertas"):
        pd.testing.assert_frame_equal(a[t], b[t])
    c = generator.gerar_instancia("media", seed=43, base=base_ficticia)
    assert not a["ofertas"].equals(c["ofertas"])


def test_precos_variam_em_torno_do_preco_base(semente):
    inst = generator.gerar_instancia("pequena", seed=3, variacao=0.15, base=semente)
    base = semente["ofertas"].groupby("produto_id")["preco_usd"].median()
    of = inst["ofertas"][inst["ofertas"]["produto_id"].isin(base.index)]
    razao = of["preco_usd"] / of["produto_id"].map(base)
    assert razao.between(0.85 - 1e-6, 1.15 + 1e-6).all()


def test_densidade_configuravel(base_ficticia):
    rala = generator.gerar_instancia("grande", seed=5, densidade=0.1, base=base_ficticia)
    densa = generator.gerar_instancia("grande", seed=5, densidade=0.8, base=base_ficticia)
    assert rala["metadata"]["densidade_efetiva"] < 0.15
    assert densa["metadata"]["densidade_efetiva"] >= 0.8


def test_salvar_instancia(semente, tmp_path):
    inst = generator.gerar_instancia("pequena", seed=42, base=semente)
    pasta = generator.salvar_instancia(inst, tmp_path / "pequena")
    for arq in ("lojas.csv", "produtos.csv", "ofertas.csv", "pontos_partida.csv", "metadata.json"):
        assert (pasta / arq).exists()
    meta = json.loads((pasta / "metadata.json").read_text())
    assert meta["seed"] == 42 and meta["tamanho"] == "pequena" and meta["densidade"] == 0.5 and meta["data_geracao"]
    # a mesma seed gera arquivos idênticos
    pasta2 = generator.salvar_instancia(generator.gerar_instancia("pequena", seed=42, base=semente), tmp_path / "b")
    for arq in ("lojas.csv", "produtos.csv", "ofertas.csv"):
        assert (pasta / arq).read_bytes() == (pasta2 / arq).read_bytes()


def test_parametros_invalidos(semente):
    with pytest.raises(ValueError, match="Tamanho inválido"):
        generator.gerar_instancia("gigante", seed=1, base=semente)
    with pytest.raises(ValueError, match="densidade"):
        generator.gerar_instancia("pequena", seed=1, densidade=0, base=semente)


def test_nao_cria_lojas_nem_produtos_artificiais(semente):
    # a semente dos testes tem 8 lojas e 18 produtos: não dá para uma instância média
    with pytest.raises(ValueError, match="Use uma base maior"):
        generator.gerar_instancia("media", seed=1, base=semente)
    inst = generator.gerar_instancia("pequena", seed=1, base=semente)
    assert set(inst["lojas"]["loja_id"]) <= set(semente["lojas"]["loja_id"])
    assert set(inst["produtos"]["produto_id"]) <= set(semente["produtos"]["produto_id"])
