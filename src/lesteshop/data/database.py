"""Banco SQLite da base de ofertas (data/lesteshop.db).

O banco não é versionado: ele é recriado a partir dos CSVs (semente em
``data/raw/``, coletas em ``data/coletas/<data>/``, catálogo e complementos
manuais das lojas).

Uso::

    python -m lesteshop.data.database --recriar                 # coletas (ou semente, se não houver coletas)
    python -m lesteshop.data.database --recriar --incluir-semente
    python -m lesteshop.data.database --vendem "playstation 5 pro"
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sqlite3
from pathlib import Path

import pandas as pd

from . import config, esquema
from .cotacao import SQL_TABELA as SQL_COTACOES
from .sources.base import FonteDeOfertas
from .sources.fonte_csv import FonteCSV
from .texto import normalizar, tokens
from .validator import validar

log = logging.getLogger(__name__)

SQL_ESQUEMA = """
CREATE TABLE IF NOT EXISTS lojas (
    loja_id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    slug TEXT,
    cidade TEXT NOT NULL,
    endereco TEXT,
    predio TEXT,
    latitude REAL,
    longitude REAL,
    coordenada_pendente INTEGER NOT NULL CHECK (coordenada_pendente IN (0, 1)),
    abre TEXT,
    fecha TEXT,
    tempo_permanencia_min REAL,
    fonte TEXT NOT NULL,
    tipo_dado TEXT NOT NULL CHECK (tipo_dado IN ('real', 'estimado', 'sintetico')),
    nome_normalizado TEXT,           -- chave sem acento/espaço (data/limpeza.py)
    zona TEXT                        -- Microcentro, Perto do microcentro, Fora do centro
);
CREATE TABLE IF NOT EXISTS produtos (
    produto_id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    categoria TEXT,
    url_modelo TEXT,
    peso_kg REAL CHECK (peso_kg IS NULL OR peso_kg > 0),
    volume_l REAL CHECK (volume_l IS NULL OR volume_l > 0),
    desconto_brasil_pct REAL CHECK (desconto_brasil_pct IS NULL OR (desconto_brasil_pct >= 0 AND desconto_brasil_pct < 1)),
    tipo_dado TEXT NOT NULL CHECK (tipo_dado IN ('real', 'estimado', 'sintetico')),
    slug TEXT                        -- único (índice abaixo): evita produto repetido no menu
);
CREATE TABLE IF NOT EXISTS ofertas (
    oferta_id INTEGER PRIMARY KEY AUTOINCREMENT,
    loja_id TEXT NOT NULL REFERENCES lojas(loja_id) ON DELETE CASCADE,
    produto_id TEXT NOT NULL REFERENCES produtos(produto_id) ON DELETE CASCADE,
    titulo_oferta TEXT,
    codigo_loja TEXT,
    preco_usd REAL NOT NULL CHECK (preco_usd > 0),
    preco_brl REAL CHECK (preco_brl IS NULL OR preco_brl > 0),
    data_coleta TEXT NOT NULL,
    fonte TEXT NOT NULL,
    tipo_dado TEXT NOT NULL CHECK (tipo_dado IN ('real', 'estimado', 'sintetico')),
    url_oferta TEXT,                 -- página do Compras Paraguai onde a oferta aparece
    coletado_em TEXT                 -- data e hora da coleta (AAAA-MM-DDTHH:MM:SS)
);
CREATE INDEX IF NOT EXISTS ix_ofertas_produto ON ofertas(produto_id, preco_usd);
CREATE TABLE IF NOT EXISTS pontos_partida (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS catalogo_modelos (
    modelo_id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    url TEXT NOT NULL,
    categoria TEXT,
    data_atualizacao TEXT
);
CREATE TABLE IF NOT EXISTS descartes_coleta (
    data TEXT, termo TEXT, url_modelo TEXT, loja_slug TEXT, cidade TEXT, motivo TEXT
);
""" + SQL_COTACOES + ";"


_COLUNAS_NOVAS = {  # 23/11/2026: bancos antigos ganham as colunas sem perder dados
    "lojas": ["nome_normalizado TEXT", "zona TEXT"],
    "produtos": ["slug TEXT"],
    "ofertas": ["url_oferta TEXT", "coletado_em TEXT"],
}


def conectar(caminho: str | Path = config.CAMINHO_BANCO) -> sqlite3.Connection:
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.execute("PRAGMA foreign_keys = ON")
    con.create_function("normalizar", 1, normalizar, deterministic=True)
    con.executescript(SQL_ESQUEMA)
    for tabela, colunas in _COLUNAS_NOVAS.items():
        existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}
        for col in colunas:
            if col.split()[0] not in existentes:
                con.execute(f"ALTER TABLE {tabela} ADD COLUMN {col}")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_produtos_slug ON produtos(slug)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_ofertas_coletado ON ofertas(coletado_em)")
    con.commit()
    return con


def _registros(df: pd.DataFrame, colunas: list[str]) -> list[tuple]:
    df = df[colunas].astype(object).where(df[colunas].notna(), None)
    return [tuple(r) for r in df.itertuples(index=False, name=None)]


def gravar(
    con: sqlite3.Connection,
    lojas: pd.DataFrame,
    produtos: pd.DataFrame,
    ofertas: pd.DataFrame,
    descartes: pd.DataFrame | None = None,
) -> None:
    """Insere ou atualiza lojas/produtos e substitui as ofertas do mesmo dia.

    Antes de gravar passa pela limpeza (``limpeza.preparar``): slug único dos produtos,
    nome normalizado e zona das lojas, lista inicial de lojas e filtro de ofertas
    (vitrine, CPO, reacondicionado, acessórios). As ofertas descartadas vão para
    ``descartes_coleta`` com o motivo."""
    from .limpeza import preparar

    limpa = preparar(lojas, produtos, ofertas)
    lojas, produtos, ofertas = limpa.lojas, limpa.produtos, limpa.ofertas
    # Slug já gravado por outro produto_id (de outra coleta): usa o produto que já existe.
    existentes = dict(con.execute("SELECT slug, produto_id FROM produtos WHERE slug IS NOT NULL"))
    troca = {pid: existentes[sl] for pid, sl in zip(produtos["produto_id"], produtos["slug"])
             if sl in existentes and existentes[sl] != pid}
    if troca:
        produtos = produtos[~produtos["produto_id"].isin(troca)]
        ofertas = ofertas.assign(produto_id=ofertas["produto_id"].map(lambda p: troca.get(p, p)))
    for aviso in limpa.avisos:
        log.info(aviso)
    if not limpa.descartes.empty:
        descartes = limpa.descartes if descartes is None or descartes.empty else \
            pd.concat([descartes, limpa.descartes], ignore_index=True)
    col_l, col_p, col_o = (esquema.COLUNAS[t] for t in ("lojas", "produtos", "ofertas"))
    lojas = esquema.padronizar(lojas, "lojas").assign(
        coordenada_pendente=lambda d: d["coordenada_pendente"].astype(int))
    with con:
        con.executemany(
            f"INSERT INTO lojas ({', '.join(col_l)}) VALUES ({', '.join('?' * len(col_l))}) "
            "ON CONFLICT(loja_id) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in col_l[1:]),
            _registros(lojas, col_l),
        )
        con.executemany(
            f"INSERT INTO produtos ({', '.join(col_p)}) VALUES ({', '.join('?' * len(col_p))}) "
            "ON CONFLICT(produto_id) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in col_p[1:]),
            _registros(esquema.padronizar(produtos, "produtos"), col_p),
        )
        ofertas = esquema.padronizar(ofertas, "ofertas")
        chaves = ofertas[["loja_id", "produto_id", "data_coleta", "fonte"]].drop_duplicates()
        con.executemany(
            "DELETE FROM ofertas WHERE loja_id=? AND produto_id=? AND data_coleta=? AND fonte=?",
            _registros(chaves, list(chaves.columns)),
        )
        con.executemany(
            f"INSERT INTO ofertas ({', '.join(col_o)}) VALUES ({', '.join('?' * len(col_o))})",
            _registros(ofertas, col_o),
        )
        if descartes is not None and not descartes.empty:
            cols = ["data", "termo", "url_modelo", "loja_slug", "cidade", "motivo"]
            con.executemany(f"INSERT INTO descartes_coleta VALUES ({', '.join('?' * len(cols))})",
                            _registros(descartes, cols))


def gravar_tabela_simples(con: sqlite3.Connection, tabela: str, df: pd.DataFrame) -> None:
    colunas = esquema.COLUNAS[tabela]
    with con:
        con.execute(f"DELETE FROM {tabela}")
        con.executemany(
            f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})",
            _registros(esquema.padronizar(df, tabela), colunas),
        )


def aplicar_complemento_lojas(lojas: pd.DataFrame, caminho: str | Path = config.CAMINHO_COMPLEMENTO_LOJAS) -> pd.DataFrame:
    """Aplica as coordenadas/prédios preenchidos à mão em data/lojas_complemento.csv."""
    caminho = Path(caminho)
    if not caminho.exists():
        return lojas
    comp = pd.read_csv(caminho, dtype=str, keep_default_na=False, na_values=[""])
    lojas = lojas.copy()
    for r in comp.itertuples():
        alvo = lojas["loja_id"] == r.loja_id
        if not alvo.any():
            continue
        for col in ("latitude", "longitude"):
            if pd.notna(getattr(r, col, None)):
                lojas.loc[alvo, col] = float(getattr(r, col))
        if pd.notna(getattr(r, "predio", None)):
            lojas.loc[alvo, "predio"] = r.predio
    lojas["coordenada_pendente"] = lojas["latitude"].isna() | lojas["longitude"].isna()
    return lojas


def pastas_de_coleta() -> list[Path]:
    if not config.DIR_COLETAS.exists():
        return []
    return sorted(p for p in config.DIR_COLETAS.iterdir() if (p / "ofertas.csv").exists())


def recriar_banco(
    caminho: str | Path = config.CAMINHO_BANCO,
    fontes: list[FonteDeOfertas] | None = None,
    incluir_semente: bool = False,
) -> sqlite3.Connection:
    """Apaga e recria o banco a partir de fontes validadas.

    Sem ``fontes``: usa as coletas salvas em data/coletas/; se não houver
    nenhuma (ou com ``incluir_semente``), usa também a base-semente de data/raw/.
    """
    if fontes is None:
        fontes = [FonteCSV(p) for p in pastas_de_coleta()]
        if incluir_semente or not fontes:
            fontes.insert(0, FonteCSV(config.DIR_RAW))
    tabelas = {"lojas": [], "produtos": [], "ofertas": []}
    for fonte in fontes:
        for nome, df in fonte.carregar_tudo().items():
            tabelas[nome].append(df)
    lojas = pd.concat(tabelas["lojas"], ignore_index=True).drop_duplicates("loja_id", keep="last")
    produtos = pd.concat(tabelas["produtos"], ignore_index=True).drop_duplicates("produto_id", keep="last")
    ofertas = pd.concat(tabelas["ofertas"], ignore_index=True)
    lojas = aplicar_complemento_lojas(lojas)
    resultado = validar(lojas, produtos, ofertas).levantar_se_invalido()
    for alerta in resultado.alertas:
        log.warning(alerta)

    caminho = Path(caminho)
    if caminho.exists():
        caminho.unlink()
    con = conectar(caminho)
    gravar(con, resultado.lojas, resultado.produtos, resultado.ofertas)
    gravar_tabela_simples(con, "pontos_partida", FonteCSV(config.DIR_RAW).carregar_pontos_partida())
    # Cotações guardadas em data/raw/cotacoes.csv servem de fallback quando a API PTAX
    # não responde (na base fictícia, é uma cotação fictícia).
    cot = FonteCSV(config.DIR_RAW).carregar_cotacoes()
    with con:
        con.executemany("INSERT OR REPLACE INTO cotacoes VALUES (?, ?, ?, ?)",
                        [(r.data, r.valor_brl_por_usd, r.fonte, r.data) for r in cot.itertuples()])
    if config.CAMINHO_CATALOGO.exists():
        cat = pd.read_csv(config.CAMINHO_CATALOGO, dtype=str, keep_default_na=False, na_values=[""])
        gravar_tabela_simples(con, "catalogo_modelos", cat.drop_duplicates("modelo_id"))
    # Descartes só das pastas que entraram no banco (e não de todas as coletas).
    for pasta in [f.pasta for f in fontes if isinstance(f, FonteCSV)]:
        arq = Path(pasta) / "descartes.csv"
        if arq.exists():
            desc = pd.read_csv(arq, dtype=str, keep_default_na=False, na_values=[""])
            with con:
                con.executemany("INSERT INTO descartes_coleta VALUES (?, ?, ?, ?, ?, ?)", _registros(desc, list(desc.columns[:6])))
    return con


def carregar_tabelas(con: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    tabelas = {}
    for nome in ("lojas", "produtos", "ofertas", "pontos_partida", "catalogo_modelos"):
        df = pd.read_sql_query(f"SELECT {', '.join(esquema.COLUNAS[nome])} FROM {nome}", con)
        tabelas[nome] = esquema.padronizar(df, nome)
    tabelas["descartes_coleta"] = pd.read_sql_query("SELECT * FROM descartes_coleta", con)
    return tabelas


SQL_OFERTAS_VALIDAS = """
WITH recentes AS (
    SELECT o.*, COALESCE(o.coletado_em, o.data_coleta) AS quando
    FROM ofertas o
    WHERE o.preco_usd > 0 AND date(COALESCE(o.coletado_em, o.data_coleta)) >= date(:desde)
      AND date(COALESCE(o.coletado_em, o.data_coleta)) <= date(:hoje)
),
ordenadas AS (
    SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.produto_id, r.loja_id
                                   ORDER BY r.preco_usd, r.quando DESC) AS pos
    FROM recentes r
)
SELECT p.produto_id, p.nome AS produto, p.slug, p.categoria,
       l.loja_id, l.nome AS loja, l.predio AS shopping_galeria, l.zona, l.latitude, l.longitude,
       MIN(o.preco_usd) AS menor_preco_usd, ROUND(AVG(o.preco_usd), 2) AS preco_medio_usd,
       COUNT(*) AS n_ofertas, MAX(o.quando) AS ultima_coleta,
       MAX(CASE WHEN o.pos = 1 THEN o.url_oferta END) AS url_oferta,
       MAX(CASE WHEN o.pos = 1 THEN o.titulo_oferta END) AS titulo_mais_barato,
       MIN(o.tipo_dado) AS tipo_dado
FROM ordenadas o
JOIN produtos p ON p.produto_id = o.produto_id
JOIN lojas l ON l.loja_id = o.loja_id
WHERE l.cidade IS NOT NULL
GROUP BY p.produto_id, l.loja_id
ORDER BY p.nome, menor_preco_usd
"""


def ofertas_validas(con: sqlite3.Connection | None = None, dias: int = 7,
                    hoje: dt.date | None = None) -> pd.DataFrame:
    """Ofertas válidas dos últimos ``dias`` dias, uma linha por produto e loja.

    Válida = gravada no banco (já passou pela limpeza: sem vitrine, CPO, reacondicionado
    nem acessório fora do lugar; só Ciudad del Este), com preço > 0 e coletada entre
    ``hoje − dias`` e ``hoje``. Por produto e loja: menor preço, preço médio, quantas
    ofertas, a coleta mais recente e a página da oferta mais barata."""
    hoje = hoje or dt.date.today()
    fechar = con is None
    con = con or conectar()
    try:
        return pd.read_sql_query(SQL_OFERTAS_VALIDAS, con, params={
            "desde": (hoje - dt.timedelta(days=dias)).isoformat(), "hoje": hoje.isoformat()})
    finally:
        if fechar:
            con.close()


def lojas_que_vendem(nome_produto: str, con: sqlite3.Connection | None = None) -> pd.DataFrame:
    """Lojas que vendem o produto (busca sem acento, todas as palavras), da
    coleta mais recente de cada loja, ordenadas pelo menor preço em US$."""
    fechar = con is None
    con = con or conectar()
    palavras = tokens(nome_produto)
    if not palavras:
        raise ValueError("Informe o nome do produto.")
    filtro = " AND ".join("(' ' || normalizar(p.nome) || ' ') LIKE ?" for _ in palavras)
    sql = f"""
        SELECT l.loja_id, l.nome AS loja, l.predio, p.produto_id, p.nome AS produto,
               o.titulo_oferta, o.preco_usd, o.preco_brl, o.data_coleta, o.tipo_dado
        FROM ofertas o
        JOIN lojas l ON l.loja_id = o.loja_id
        JOIN produtos p ON p.produto_id = o.produto_id
        WHERE {filtro}
          AND o.data_coleta = (SELECT MAX(o2.data_coleta) FROM ofertas o2
                               WHERE o2.loja_id = o.loja_id AND o2.produto_id = o.produto_id)
        ORDER BY o.preco_usd ASC, l.nome ASC
    """
    try:
        return pd.read_sql_query(sql, con, params=[f"% {p}%" for p in palavras])
    finally:
        if fechar:
            con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cria/recria o banco SQLite do LesteShop.")
    parser.add_argument("--banco", default=str(config.CAMINHO_BANCO))
    parser.add_argument("--recriar", action="store_true", help="apaga e recria o banco a partir dos CSVs")
    parser.add_argument("--incluir-semente", action="store_true", help="inclui a base-semente (data/raw) junto com as coletas")
    parser.add_argument("--vendem", metavar="PRODUTO", help="lista as lojas que vendem o produto")
    args = parser.parse_args(argv)
    if args.recriar:
        con = recriar_banco(args.banco, incluir_semente=args.incluir_semente)
        n = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("lojas", "produtos", "ofertas")}
        print(f"Banco recriado em {args.banco}: {n['lojas']} lojas, {n['produtos']} produtos, {n['ofertas']} ofertas.")
    if args.vendem:
        df = lojas_que_vendem(args.vendem, conectar(args.banco))
        print(df.to_string(index=False) if not df.empty else "Nenhuma loja encontrada.")
    if not (args.recriar or args.vendem):
        parser.print_help()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
