"""Base de ofertas usada pelo app.

Lê o banco SQLite (``data/lesteshop.db``); se ele não existir, recria a partir dos
CSVs com ``database.recriar_banco()`` (coletas de ``data/coletas/`` se houver,
senão a base fictícia de ``data/raw/``).

Decisões (Fase 4):

* de cada par (loja, produto) vale só a **coleta mais recente**; só depois disso a
  regra da Fase 2 (oferta repetida na mesma loja → menor preço) é aplicada;
* a base é **real** só se todas as ofertas forem ``tipo_dado = "real"``; caso
  contrário, a tela a identifica como fictícia (ou mista);
* o turista só escolhe produtos que têm pelo menos uma oferta na base;
* **preço atípico** (decidido em 20/11/2026): oferta com preço menor que a metade da
  mediana das ofertas do mesmo produto (com 3 ofertas ou mais) é descartada, com aviso.
  No site real, lojas cadastram outros produtos na página de um modelo (ex.: fones de
  US$ 9 na página do iPad); sem a regra, o app "compraria" o iPad por US$ 9.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..data import config, database
from ..data.cotacao import Cotacao, ErroCotacao, obter_cotacao


@dataclass
class BaseApp:
    lojas: pd.DataFrame
    produtos: pd.DataFrame          # só os que têm oferta, ordenados pelo nome
    ofertas: pd.DataFrame           # só a coleta mais recente de cada (loja, produto)
    pontos: pd.DataFrame
    caminho_banco: Path
    avisos_produto: dict[str, list[str]] = field(default_factory=dict)  # produto_id -> avisos

    @property
    def origem(self) -> str:
        """``"real"``, ``"ficticia"`` ou ``"mista"``."""
        tipos = set(self.ofertas["tipo_dado"].dropna())
        if tipos == {"real"}:
            return "real"
        if "real" in tipos:
            return "mista"
        return "ficticia"

    @property
    def data_coleta(self) -> tuple[str | None, str | None]:
        """Data mais antiga e mais recente das ofertas (AAAA-MM-DD)."""
        datas = self.ofertas["data_coleta"].dropna()
        if datas.empty:
            return None, None
        return str(datas.min()), str(datas.max())

    @property
    def n_lojas(self) -> int:
        return len(self.lojas)

    def nome_produto(self, produto_id: str) -> str:
        linha = self.produtos[self.produtos["produto_id"] == produto_id]
        return str(linha.iloc[0]["nome"]) if not linha.empty else produto_id

    def info_oferta(self, loja_id: str, produto_id: str) -> dict:
        """Data da coleta e tipo de dado da oferta usada (mais recente, menor preço)."""
        of = self.ofertas[(self.ofertas["loja_id"] == loja_id) & (self.ofertas["produto_id"] == produto_id)]
        if of.empty:
            return {"data_coleta": None, "tipo_dado": None}
        linha = of.sort_values("preco_usd").iloc[0]
        return {"data_coleta": linha["data_coleta"], "tipo_dado": linha["tipo_dado"]}


def so_mais_recente(ofertas: pd.DataFrame) -> pd.DataFrame:
    """Mantém, de cada (loja, produto), só as ofertas da data de coleta mais recente."""
    if ofertas.empty:
        return ofertas
    ultima = ofertas.groupby(["loja_id", "produto_id"])["data_coleta"].transform("max")
    return ofertas[ofertas["data_coleta"] == ultima].reset_index(drop=True)


FATOR_PRECO_ATIPICO = 0.5
MIN_OFERTAS_PRECO_ATIPICO = 3


def descartar_precos_atipicos(ofertas: pd.DataFrame, nomes: dict[str, str] | None = None
                              ) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Tira as ofertas com preço < ``FATOR_PRECO_ATIPICO`` × mediana do produto.

    Devolve as ofertas que ficam e, por produto, o aviso das descartadas."""
    if ofertas.empty:
        return ofertas, {}
    n = ofertas.groupby("produto_id")["preco_usd"].transform("size")
    mediana = ofertas.groupby("produto_id")["preco_usd"].transform("median")
    atipica = (n >= MIN_OFERTAS_PRECO_ATIPICO) & (ofertas["preco_usd"] < FATOR_PRECO_ATIPICO * mediana)
    avisos: dict[str, list[str]] = {}
    for pid, grupo in ofertas[atipica].groupby("produto_id"):
        nome = (nomes or {}).get(pid, pid)
        exemplos = ", ".join(f"{t} (US$ {p:.2f})" for t, p in
                             zip(grupo["titulo_oferta"].fillna("?"), grupo["preco_usd"]))
        avisos[pid] = [f"{len(grupo)} oferta(s) de {nome} descartada(s) por preço menor que a metade "
                       f"do preço mediano (provável outro produto cadastrado na página): {exemplos}."]
    return ofertas[~atipica].reset_index(drop=True), avisos


def carregar_base(caminho: str | Path = config.CAMINHO_BANCO, recriar: bool = False) -> BaseApp:
    """Lê a base do SQLite (recriando-o se não existir ou se ``recriar``)."""
    caminho = Path(caminho)
    if recriar or not caminho.exists():
        con = database.recriar_banco(caminho)
    else:
        con = database.conectar(caminho)
    try:
        tab = database.carregar_tabelas(con)
    finally:
        con.close()
    ofertas = so_mais_recente(tab["ofertas"])
    nomes = dict(zip(tab["produtos"]["produto_id"], tab["produtos"]["nome"]))
    ofertas, avisos = descartar_precos_atipicos(ofertas, nomes)
    com_oferta = set(ofertas["produto_id"])
    produtos = (tab["produtos"][tab["produtos"]["produto_id"].isin(com_oferta)]
                .sort_values("nome", key=lambda s: s.str.lower()).reset_index(drop=True))
    return BaseApp(lojas=tab["lojas"], produtos=produtos, ofertas=ofertas,
                   pontos=tab["pontos_partida"], caminho_banco=caminho, avisos_produto=avisos)


def ofertas_antigas(base: BaseApp, produto_ids: list[str], hoje: dt.date | None = None) -> list[str]:
    """Avisos para os produtos cuja oferta mais recente tem mais de
    ``DIAS_VALIDADE_OFERTA`` dias (a oferta continua sendo usada)."""
    hoje = hoje or dt.date.today()
    avisos = []
    for pid in produto_ids:
        datas = base.ofertas.loc[base.ofertas["produto_id"] == pid, "data_coleta"].dropna()
        if datas.empty:
            continue
        mais_recente = dt.date.fromisoformat(str(datas.max()))
        dias = (hoje - mais_recente).days
        if dias > config.DIAS_VALIDADE_OFERTA:
            avisos.append(f"Os preços de {base.nome_produto(pid)} foram coletados em "
                          f"{mais_recente:%d/%m/%Y} ({dias} dias atrás) e podem ter mudado.")
    return avisos


def cotacao_para_exibir(caminho: str | Path = config.CAMINHO_BANCO) -> Cotacao | None:
    """PTAX do dia (ou a última guardada no banco); ``None`` se não houver nenhuma."""
    con = database.conectar(caminho)
    try:
        return obter_cotacao(con=con)
    except ErroCotacao:
        return None
    finally:
        con.close()
