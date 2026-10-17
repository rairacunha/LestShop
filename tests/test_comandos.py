"""Testa os comandos de linha de comando de ponta a ponta, sem internet."""

import datetime as dt

import pandas as pd

from lesteshop.data import coletar, config, database, resumo
from lesteshop.data.sources import FonteComprasParaguai


def test_comando_coletar_grava_csv_e_banco(monkeypatch, tmp_path, cliente_falso, capsys):
    monkeypatch.setattr(config, "DIR_COLETAS", tmp_path / "coletas")
    original = FonteComprasParaguai

    def fonte_offline(**kw):
        kw.pop("cliente", None)
        return original(cliente=cliente_falso, dir_cache_lojas=tmp_path / "lojas", **kw)

    monkeypatch.setattr(coletar, "FonteComprasParaguai", fonte_offline)
    banco = tmp_path / "t.db"
    assert coletar.main(["playstation 5 pro", "--banco", str(banco)]) == 0
    saida = capsys.readouterr().out
    assert "3 oferta(s) em Ciudad del Este" in saida
    assert "2 oferta(s) descartada(s) por cidade" in saida
    assert "CP-games-del-este" in saida  # coordenada pendente listada
    hoje = dt.date.today().isoformat()
    assert len(pd.read_csv(tmp_path / "coletas" / hoje / "ofertas.csv")) == 3
    # rodar de novo no mesmo dia não duplica
    assert coletar.main(["playstation 5 pro", "--banco", str(banco)]) == 0
    assert len(pd.read_csv(tmp_path / "coletas" / hoje / "ofertas.csv")) == 3
    con = database.conectar(banco)
    assert con.execute("SELECT COUNT(*) FROM ofertas").fetchone()[0] == 3


def test_resumo_imprime_e_exporta(tmp_path, capsys):
    con = database.recriar_banco(tmp_path / "r.db", fontes=[database.FonteCSV()])
    con.close()
    assert resumo.main(["--banco", str(tmp_path / "r.db"), "--sem-cotacao", "--export", str(tmp_path / "exp")]) == 0
    saida = capsys.readouterr().out
    assert "Lojas: 8   Produtos: 18" in saida and "coordenada pendente: 1" in saida and "Validação: OK" in saida
    for arq in ("lojas.csv", "produtos.csv", "ofertas.csv"):
        assert (tmp_path / "exp" / arq).exists()
