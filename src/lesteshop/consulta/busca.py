"""Consulta sob demanda: só os itens escolhidos pelo turista.

Para cada item do catálogo curado:

1. se o resultado está no cache e tem menos de 6 h, usa o cache (nenhuma requisição);
2. senão, acessa o Compras Paraguai: a página do modelo (direto pela ``url_modelo``
   ou pela busca do ``termo``) e, para cada loja de Ciudad del Este que vende o
   produto, a página da loja (endereço, coordenadas e horário; cache permanente);
3. extrai preço em US$ e loja de cada oferta e grava no cache.

Boas práticas de tráfego (herdadas de ``ClienteHTTP``): robots.txt respeitado,
intervalo mínimo entre requisições (``config.INTERVALO_S``, ou o Crawl-delay do
robots.txt se for maior), identificação do projeto acadêmico e nenhuma tentativa de
contornar a verificação anti-robô (no computador, ``ClienteNavegador``: a pessoa a
resolve).

O resultado vira a matriz Produto × Loja × Preço e uma ``BaseApp``, que o app passa
ao modelo de otimização da Fase 2 (sem mudanças).
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from ..app.base import BaseApp, so_mais_recente
from ..data import config as config_dados
from ..data import esquema
from ..data.database import aplicar_complemento_lojas
from ..data.sources.comprasparaguai import FonteComprasParaguai
from ..data.sources.fonte_csv import FonteCSV
from ..data.sources.http import ClienteHTTP, ErroColeta
from ..data.sources.parser_cp import ErroEstruturaHTML
from ..data.validator import validar
from ..fiscal.categorias import Classificacao, MapaCategorias, carregar_categorias
from . import config
from .cache import CacheConsulta
from .catalogo import ItemCatalogo

log = logging.getLogger(__name__)


@dataclass
class ResultadoConsulta:
    produtos: pd.DataFrame
    lojas: pd.DataFrame
    ofertas: pd.DataFrame
    por_item: dict[str, str] = field(default_factory=dict)         # item_id -> produto_id
    nome_no_site: dict[str, str] = field(default_factory=dict)     # item_id -> nome do modelo no site
    consultado_em: dict[str, str] = field(default_factory=dict)    # item_id -> AAAA-MM-DDTHH:MM
    do_cache: list[str] = field(default_factory=list)
    nao_encontrados: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    requisicoes: int = 0

    def matriz(self) -> pd.DataFrame:
        """Matriz Produto × Loja × Preço (formato longo, uma linha por oferta)."""
        if self.ofertas.empty:
            return pd.DataFrame(columns=["produto_id", "produto", "loja_id", "loja", "preco_usd"])
        m = (self.ofertas.merge(self.produtos[["produto_id", "nome"]].rename(columns={"nome": "produto"}),
                                on="produto_id")
             .merge(self.lojas[["loja_id", "nome"]].rename(columns={"nome": "loja"}), on="loja_id"))
        m = m.groupby(["produto_id", "produto", "loja_id", "loja"], as_index=False)["preco_usd"].min()
        return m.sort_values(["produto", "preco_usd"]).reset_index(drop=True)


def _registros(df: pd.DataFrame) -> list[dict]:
    return df.astype(object).where(df.notna(), None).to_dict("records")


def _consultar_item(item: ItemCatalogo, cliente: ClienteHTTP, dir_cache_lojas=None) -> dict | None:
    """Acessa o site para um item; ``None`` se o site não tem o produto em CDE."""
    fonte = FonteComprasParaguai(
        termos=[] if item.url_modelo else [item.termo],
        urls_modelos=[item.url_modelo] if item.url_modelo else [],
        categoria=item.categoria, cliente=cliente, dir_cache_lojas=dir_cache_lojas,
    )
    res = fonte.coletar()
    if res.produtos.empty or res.ofertas.empty:
        return None
    val = validar(res.lojas, res.produtos, res.ofertas)
    if not val.ok:
        raise ErroEstruturaHTML("dados fora do padrão: " + "; ".join(val.erros))
    return {
        "produto": _registros(val.produtos.head(1))[0],
        "lojas": _registros(val.lojas),
        "ofertas": _registros(val.ofertas),
        "consultado_em": dt.datetime.now().isoformat(timespec="minutes"),
    }


def consultar(
    itens: list[ItemCatalogo],
    criar_cliente: Callable[[], ClienteHTTP],
    cache: CacheConsulta | None = None,
    progresso: Callable[[str], None] | None = None,
    dir_cache_lojas=None,
) -> ResultadoConsulta:
    """Consulta os ``itens`` (cache primeiro). ``criar_cliente`` só é chamado se
    algum item precisar ir ao site; o cliente é fechado no fim. ``dir_cache_lojas``:
    pasta do cache permanente das páginas de loja (padrão ``data/cache/lojas/``)."""
    cache = cache or CacheConsulta()
    avisar = progresso or (lambda _m: None)
    produtos, lojas, ofertas = [], [], []
    res = ResultadoConsulta(esquema.vazio("produtos"), esquema.vazio("lojas"), esquema.vazio("ofertas"))
    cliente = None
    try:
        for n, item in enumerate(itens, start=1):
            dados = cache.obter(item.id)
            if dados is not None:
                res.do_cache.append(item.id)
                avisar(f"{n}/{len(itens)} {item.nome}: preços guardados de {dados['consultado_em'][11:16]}")
            else:
                avisar(f"{n}/{len(itens)} {item.nome}: consultando o Compras Paraguai…")
                try:
                    if cliente is None:
                        cliente = criar_cliente()
                    dados = _consultar_item(item, cliente, dir_cache_lojas)
                except ErroEstruturaHTML as e:
                    res.avisos.append(f"{item.nome}: não foi possível ler a página do site ({e}).")
                    res.nao_encontrados.append(item.id)
                    continue
                except ErroColeta as e:
                    restantes = [i.nome for i in itens[n - 1:]]
                    res.avisos.append(f"Consulta interrompida: {e} Itens sem consulta: {', '.join(restantes)}.")
                    res.nao_encontrados.extend(i.id for i in itens[n - 1:])
                    break
                if dados is None:
                    res.avisos.append(f"{item.nome}: nenhuma oferta em Ciudad del Este no Compras Paraguai.")
                    res.nao_encontrados.append(item.id)
                    continue
                cache.gravar(item.id, dados)
            produtos.append(dados["produto"])
            lojas.extend(dados["lojas"])
            ofertas.extend(dados["ofertas"])
            res.por_item[item.id] = dados["produto"]["produto_id"]
            res.nome_no_site[item.id] = dados["produto"]["nome"]
            res.consultado_em[item.id] = dados["consultado_em"]
    finally:
        if cliente is not None:
            res.requisicoes = cliente.requisicoes
            if hasattr(cliente, "fechar"):
                cliente.fechar()

    res.produtos = esquema.padronizar(pd.DataFrame(produtos, columns=esquema.COLUNAS["produtos"]), "produtos") \
        .drop_duplicates("produto_id").reset_index(drop=True)
    res.lojas = esquema.padronizar(pd.DataFrame(lojas, columns=esquema.COLUNAS["lojas"]), "lojas") \
        .drop_duplicates("loja_id", keep="last").reset_index(drop=True)
    res.ofertas = esquema.padronizar(pd.DataFrame(ofertas, columns=esquema.COLUNAS["ofertas"]), "ofertas")
    return res


def para_base(res: ResultadoConsulta) -> BaseApp:
    """Base do app a partir da consulta (com as correções de ``lojas_complemento.csv``)."""
    return BaseApp(
        lojas=aplicar_complemento_lojas(res.lojas),
        produtos=res.produtos.sort_values("nome").reset_index(drop=True),
        ofertas=so_mais_recente(res.ofertas),
        pontos=FonteCSV(config_dados.DIR_RAW).carregar_pontos_partida(),
        caminho_banco=config.CAMINHO_CACHE,
    )


def mapa_categorias(itens: list[ItemCatalogo], res: ResultadoConsulta) -> MapaCategorias:
    """Categorias fiscais de ``categorias_fiscais.csv`` + o conteúdo (litros) das
    bebidas informado no catálogo curado, ligado ao produto encontrado no site."""
    base = carregar_categorias()
    extra = {}
    for it in itens:
        pid = res.por_item.get(it.id)
        if pid and it.conteudo_por_unidade is not None and pid not in base.por_produto:
            fiscal = base.classificar(pid, it.categoria).categoria_fiscal
            extra[pid] = Classificacao(fiscal, it.conteudo_por_unidade)
    return MapaCategorias(base.por_categoria, {**base.por_produto, **extra})


def criar_cliente_navegador() -> ClienteHTTP:
    """Cliente do app no computador: janela do Chromium (a pessoa resolve a
    verificação anti-robô, se aparecer), intervalo da consulta e sem o cache
    diário de páginas (quem controla a validade é o ``CacheConsulta``)."""
    from ..data.sources.navegador import ClienteNavegador

    return ClienteNavegador(intervalo=config.INTERVALO_S, cache_paginas=False)
