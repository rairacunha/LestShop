"""Testa os comandos de linha de comando de ponta a ponta, sem internet."""

import datetime as dt

import pandas as pd

from lesteshop.data import coletar, config, database, resumo
from lesteshop.data.sources import FonteComprasParaguai

from conftest import SEMENTE


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
    con = database.recriar_banco(tmp_path / "r.db", fontes=[database.FonteCSV(SEMENTE)])
    con.close()
    assert resumo.main(["--banco", str(tmp_path / "r.db"), "--sem-cotacao", "--export", str(tmp_path / "exp")]) == 0
    saida = capsys.readouterr().out
    assert "Lojas: 8   Produtos: 18" in saida and "coordenada pendente: 1" in saida and "Validação: OK" in saida
    for arq in ("lojas.csv", "produtos.csv", "ofertas.csv"):
        assert (tmp_path / "exp" / arq).exists()


def test_coletar_por_arquivo_segue_mesmo_com_erro(monkeypatch, tmp_path, cliente_falso, capsys):
    """--arquivo: cada termo com a sua categoria; um termo com erro não impede os outros."""
    import json

    from lesteshop.data.sources.http import ErroColeta

    monkeypatch.setattr(config, "DIR_COLETAS", tmp_path / "coletas")
    original = FonteComprasParaguai
    categorias = []

    def fonte_offline(**kw):
        kw.pop("cliente", None)
        categorias.append((kw.get("termos"), kw.get("categoria")))
        fonte = original(cliente=cliente_falso, dir_cache_lojas=tmp_path / "lojas", **kw)
        if kw.get("termos") == ["termo quebrado"]:
            fonte.coletar = lambda: (_ for _ in ()).throw(ErroColeta("site fora do ar"))
        return fonte

    monkeypatch.setattr(coletar, "FonteComprasParaguai", fonte_offline)
    arq = tmp_path / "lista.json"
    arq.write_text(json.dumps([{"termo": "playstation 5 pro", "categoria": "Games"},
                               {"termo": "termo quebrado", "categoria": "Outros"}]), encoding="utf-8")
    codigo = coletar.main(["--arquivo", str(arq), "avulso", "--categoria", "Geral",
                           "--banco", str(tmp_path / "t.db")])
    saida = capsys.readouterr().out
    assert codigo == 1  # houve falha, mas o que deu certo foi gravado
    assert "[Games] (1/3) Coletando 'playstation 5 pro'" in saida and "Resumo da coleta" in saida
    assert "'termo quebrado': FALHOU: site fora do ar" in saida
    assert (["playstation 5 pro"], "Games") in categorias and (["avulso"], "Geral") in categorias
    con = database.conectar(tmp_path / "t.db")
    assert con.execute("SELECT COUNT(*) FROM ofertas").fetchone()[0] == 3


def test_carregar_fila_valida_o_arquivo(tmp_path):
    import json

    import pytest

    arq = tmp_path / "a.json"
    arq.write_text(json.dumps([{"termo": "ipad"}, {"termo": "IPAD", "categoria": "X"}]), encoding="utf-8")
    assert coletar.carregar_fila(["mouse"], "Geral", str(arq)) == [
        {"termo": "ipad", "categoria": "Geral"}, {"termo": "mouse", "categoria": "Geral"}]
    arq.write_text(json.dumps([{"categoria": "X"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="termo"):
        coletar.carregar_fila([], None, str(arq))


def test_url_da_pagina_preserva_parametros():
    from lesteshop.data.sources.comprasparaguai import url_da_pagina

    base = "https://www.comprasparaguai.com.br/celular/"
    assert url_da_pagina(base, 1) == base
    assert url_da_pagina(base, 2) == base + "?page=2"
    assert url_da_pagina(base + "?ordem=relevancia", 3) == base + "?ordem=relevancia&page=3"
    assert url_da_pagina(base + "?page=5&ordem=menor-preco", 2) == base + "?page=2&ordem=menor-preco"
    assert url_da_pagina(base + "?page=5", 1) == base + "?page=1"


def test_coletar_por_url_categoria(monkeypatch, tmp_path, cliente_falso, capsys):
    """--url-categoria: lê os cards com o mesmo leitor da busca, pagina pelo parâmetro page
    (preservando os outros), respeita o intervalo e grava pelo mesmo caminho."""
    import pytest

    monkeypatch.setattr(config, "DIR_COLETAS", tmp_path / "coletas")
    url = f"{config.URL_BASE_CP}/games/?ordem=relevancia"
    rotas = cliente_falso.sessao_falsa.rotas
    rotas[url] = "busca_playstation.html"
    rotas[url + "&page=2"] = "busca_playstation.html"    # sem modelo novo: para aqui
    original = FonteComprasParaguai

    def fonte_offline(**kw):
        kw.pop("cliente", None)
        return original(cliente=cliente_falso, dir_cache_lojas=tmp_path / "lojas", **kw)

    monkeypatch.setattr(coletar, "FonteComprasParaguai", fonte_offline)
    with pytest.raises(SystemExit):     # --url-categoria sem --categoria
        coletar.main(["--url-categoria", url])
    banco = tmp_path / "t.db"
    assert coletar.main(["--url-categoria", url, "--categoria", "Games", "--paginas", "3", "--max-modelos", "1",
                         "--banco", str(banco)]) == 0
    acessos = cliente_falso.sessao_falsa.acessos
    assert url in acessos and url + "&page=2" in acessos and url + "&page=3" not in acessos
    assert all(e <= config.INTERVALO_MIN_SEGUNDOS for e in cliente_falso.esperas) and cliente_falso.esperas
    con = database.conectar(banco)
    assert con.execute("SELECT DISTINCT categoria FROM produtos").fetchall() == [("Games",)]
    assert con.execute("SELECT COUNT(*) FROM ofertas WHERE url_oferta IS NOT NULL AND coletado_em IS NOT NULL").fetchone()[0] == 3
    assert "3 oferta(s) em Ciudad del Este" in capsys.readouterr().out
