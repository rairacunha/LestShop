"""Catálogo local de modelos do Compras Paraguai (base do futuro autocompletar).

O catálogo vem do sitemap indicado no robots.txt e fica versionado em
``data/catalogo_modelos.csv``. A busca :func:`sugerir_modelos` é feita só no
arquivo local, sem internet.

Uso::

    python -m lesteshop.data.catalogo atualizar     # baixa o sitemap (10 s entre requisições)
    python -m lesteshop.data.catalogo sugerir "playstation 5 pro"
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import gzip
import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd

from . import config, esquema
from .sources.http import ClienteHTTP, ErroColeta
from .sources.parser_cp import RE_URL_MODELO
from .texto import nome_de_slug, tokens

log = logging.getLogger(__name__)


class ErroCatalogo(RuntimeError):
    """A atualização do catálogo falhou; o arquivo existente não foi alterado."""


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def ler_sitemap(conteudo: bytes) -> tuple[list[tuple[str, str | None]], list[str]]:
    """Devolve (urls com lastmod, sitemaps filhos) de um sitemap ou índice."""
    if conteudo[:2] == b"\x1f\x8b":
        conteudo = gzip.decompress(conteudo)
    try:
        raiz = ET.fromstring(conteudo)
    except ET.ParseError as e:
        raise ErroCatalogo(f"O sitemap não é um XML válido ({e}). O site pode ter mudado.") from e
    if _local(raiz.tag) not in ("urlset", "sitemapindex"):
        raise ErroCatalogo(f"Sitemap com raiz inesperada <{_local(raiz.tag)}>; esperava <urlset> ou <sitemapindex>.")
    urls, filhos = [], []
    for item in raiz:
        campos = {_local(c.tag): (c.text or "").strip() for c in item}
        loc = campos.get("loc")
        if not loc:
            continue
        if _local(item.tag) == "sitemap":
            filhos.append(loc)
        elif _local(item.tag) == "url":
            urls.append((loc, campos.get("lastmod") or None))
    return urls, filhos


def modelo_de_url(url: str) -> dict | None:
    """Linha do catálogo para uma URL de modelo (``/<slug>_<id>/``) ou None."""
    partes = urlsplit(url)
    m = RE_URL_MODELO.match(partes.path)
    if not m:
        return None
    return {
        "modelo_id": f"CP-{m.group('id')}",
        "nome": nome_de_slug(m.group("slug")),
        "url": f"{config.URL_BASE_CP}{partes.path.rstrip('/')}/",
        "categoria": None,
    }


def coletar_catalogo(cliente: ClienteHTTP, max_sitemaps: int | None = None) -> pd.DataFrame:
    """Percorre o sitemap (e os filhos, se for um índice) e extrai os modelos."""
    pendentes = cliente.sitemaps_do_robots(config.URL_BASE_CP) or [f"{config.URL_BASE_CP}/sitemap.xml"]
    vistos: set[str] = set()
    modelos: dict[str, dict] = {}
    while pendentes:
        url = pendentes.pop(0)
        if url in vistos:
            continue
        if max_sitemaps is not None and len(vistos) >= max_sitemaps:
            log.warning("Limite de %d sitemaps atingido; restantes ignorados.", max_sitemaps)
            break
        vistos.add(url)
        urls, filhos = ler_sitemap(cliente.get_bytes(url))
        pendentes.extend(f for f in filhos if f not in vistos)
        for loc, _lastmod in urls:
            linha = modelo_de_url(loc)
            if linha:
                modelos[linha["modelo_id"]] = linha
        log.info("Sitemap %s: %d URLs, %d filhos; %d modelos até agora.", url, len(urls), len(filhos), len(modelos))
    return pd.DataFrame(list(modelos.values()), columns=esquema.COLUNAS["catalogo_modelos"][:-1])


# ---------------------------------------------------------------------------
# Atualização do CSV versionado
# ---------------------------------------------------------------------------
def carregar_catalogo(caminho: str | Path = config.CAMINHO_CATALOGO) -> pd.DataFrame:
    caminho = Path(caminho)
    if not caminho.exists():
        return esquema.vazio("catalogo_modelos")
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False, na_values=[""])
    return esquema.padronizar(df, "catalogo_modelos")


def mesclar_catalogo(antigo: pd.DataFrame, novo: pd.DataFrame, hoje: dt.date) -> tuple[pd.DataFrame, int, int]:
    """Mantém a data_atualizacao dos modelos inalterados; novos/alterados recebem ``hoje``."""
    antigo_idx = antigo.set_index("modelo_id")
    linhas = []
    for r in novo.itertuples(index=False):
        if r.modelo_id in antigo_idx.index:
            velho = antigo_idx.loc[r.modelo_id]
            mudou = velho["nome"] != r.nome or velho["url"] != r.url
            data = hoje.isoformat() if mudou else velho["data_atualizacao"]
            categoria = r.categoria if r.categoria else velho["categoria"]
        else:
            data, categoria = hoje.isoformat(), r.categoria
        linhas.append({"modelo_id": r.modelo_id, "nome": r.nome, "url": r.url,
                       "categoria": categoria, "data_atualizacao": data})
    df = pd.DataFrame(linhas, columns=esquema.COLUNAS["catalogo_modelos"])
    df = df.sort_values("modelo_id", key=lambda s: s.str.extract(r"(\d+)$")[0].astype(int)).reset_index(drop=True)
    novos = len(set(novo["modelo_id"]) - set(antigo["modelo_id"]))
    removidos = len(set(antigo["modelo_id"]) - set(novo["modelo_id"]))
    return df, novos, removidos


def atualizar_catalogo(
    caminho: str | Path = config.CAMINHO_CATALOGO,
    caminho_meta: str | Path = config.CAMINHO_META_CATALOGO,
    cliente: ClienteHTTP | None = None,
    hoje: dt.date | None = None,
    fracao_minima: float = 0.5,
    max_sitemaps: int | None = None,
) -> dict:
    """Baixa o sitemap e reescreve o CSV. Em qualquer falha, o CSV antigo fica intacto.

    Também recusa o resultado se ele tiver menos de ``fracao_minima`` dos modelos
    atuais (sinal de que o sitemap veio incompleto ou mudou de formato).
    """
    hoje = hoje or dt.date.today()
    caminho, caminho_meta = Path(caminho), Path(caminho_meta)
    cliente = cliente or ClienteHTTP(hoje=hoje)
    antigo = carregar_catalogo(caminho)
    try:
        novo = coletar_catalogo(cliente, max_sitemaps=max_sitemaps)
    except ErroColeta as e:
        raise ErroCatalogo(f"Falha ao baixar o sitemap: {e}") from e
    if novo.empty:
        raise ErroCatalogo("O sitemap não trouxe nenhuma URL de modelo (/<slug>_<id>/). "
                           "O site pode estar fora do ar ou ter mudado; catálogo mantido.")
    if len(antigo) >= 100 and len(novo) < fracao_minima * len(antigo):
        raise ErroCatalogo(f"O sitemap trouxe só {len(novo)} modelos contra {len(antigo)} no catálogo atual; "
                           "resultado suspeito, catálogo mantido.")
    df, novos, removidos = mesclar_catalogo(antigo, novo, hoje)

    temporario = caminho.with_suffix(".csv.tmp")
    df.to_csv(temporario, index=False)
    os.replace(temporario, caminho)
    meta = {"ultima_atualizacao": hoje.isoformat(), "total": len(df), "novos": novos,
            "removidos": removidos, "fonte": config.URL_BASE_CP + "/sitemap.xml"}
    caminho_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _INDICES.clear()
    return meta


# ---------------------------------------------------------------------------
# Busca local (autocompletar)
# ---------------------------------------------------------------------------
class IndiceCatalogo:
    """Índice invertido por palavra, com busca por prefixo via ``bisect``.

    Ignora maiúsculas, acentos e ordem das palavras: todas as palavras digitadas
    precisam aparecer (como palavra inteira ou início de palavra) no nome.
    """

    def __init__(self, catalogo: pd.DataFrame):
        self.catalogo = catalogo.reset_index(drop=True)
        self._tokens: list[list[str]] = [tokens(n) for n in self.catalogo["nome"]]
        self._norm: list[str] = [" ".join(t) for t in self._tokens]
        indice: dict[str, list[int]] = {}
        for i, toks in enumerate(self._tokens):
            for t in dict.fromkeys(toks):
                indice.setdefault(t, []).append(i)
        # Vocabulário ordenado + linhas de cada palavra num único array (formato CSR):
        # as linhas das palavras com um prefixo são uma fatia contígua de _linhas.
        self._vocab = sorted(indice)
        tamanhos = np.fromiter((len(indice[p]) for p in self._vocab), dtype=np.int64, count=len(self._vocab))
        self._inicio = np.concatenate([[0], np.cumsum(tamanhos)]).astype(np.int64)
        self._linhas = np.fromiter((i for p in self._vocab for i in indice[p]), dtype=np.int64,
                                   count=int(self._inicio[-1]))
        # Ordem "estática": nomes mais curtos primeiro, depois alfabética.
        ordem = sorted(range(len(self._tokens)), key=lambda i: (len(self._tokens[i]), self._norm[i]))
        self._rank = np.empty(len(ordem), dtype=np.int64)
        self._rank[ordem] = np.arange(len(ordem))
        if self._vocab:
            self.sugerir(self._vocab[0])  # aquece numpy, para a 1ª consulta já ser rápida

    def _faixa(self, palavra: str, prefixo: bool) -> np.ndarray:
        ini = bisect.bisect_left(self._vocab, palavra)
        if prefixo:
            fim = bisect.bisect_left(self._vocab, palavra + "\uffff")
        else:
            fim = ini + 1 if ini < len(self._vocab) and self._vocab[ini] == palavra else ini
        return self._linhas[self._inicio[ini]:self._inicio[fim]]

    def sugerir(self, texto: str, limite: int = 10) -> pd.DataFrame:
        consulta = tokens(texto)
        if not consulta or limite <= 0:
            return self.catalogo.iloc[0:0]
        n = len(self._rank)
        mascara = np.ones(n, dtype=bool)
        for t in set(consulta):
            achados = np.zeros(n, dtype=bool)
            achados[self._faixa(t, prefixo=True)] = True
            mascara &= achados
        cand = np.flatnonzero(mascara)
        if cand.size == 0:
            return self.catalogo.iloc[0:0]

        # Pré-seleção vetorizada: mais palavras exatas e nome mais curto.
        exatas = np.zeros(n, dtype=np.int64)
        for t in consulta:
            exatas[self._faixa(t, prefixo=False)] += 1
        chave = -exatas[cand] * n + self._rank[cand]
        reserva = limite * 20
        if cand.size > reserva:
            cand = cand[np.argpartition(chave, reserva)[:reserva]]

        consulta_norm = " ".join(consulta)

        def pontuacao(i: int) -> tuple:
            toks = self._tokens[i]
            return (-sum(t in toks for t in consulta), consulta_norm not in self._norm[i], int(self._rank[i]))

        melhores = sorted(cand.tolist(), key=pontuacao)[:limite]
        return self.catalogo.iloc[melhores].reset_index(drop=True)


_INDICES: dict[tuple[str, float], IndiceCatalogo] = {}


def indice_catalogo(caminho: str | Path = config.CAMINHO_CATALOGO) -> IndiceCatalogo:
    caminho = Path(caminho)
    chave = (str(caminho.resolve()), caminho.stat().st_mtime if caminho.exists() else 0.0)
    if chave not in _INDICES:
        _INDICES.clear()
        _INDICES[chave] = IndiceCatalogo(carregar_catalogo(caminho))
    return _INDICES[chave]


def sugerir_modelos(texto: str, limite: int = 10, caminho: str | Path = config.CAMINHO_CATALOGO) -> pd.DataFrame:
    """Até ``limite`` modelos do catálogo local que combinam com ``texto``.

    Não acessa a internet. Ex.: "playstation 5 pro" acha
    "Sony Playstation 5 Pro 2TB Digital Edition".
    """
    return indice_catalogo(caminho).sugerir(texto, limite)


# ---------------------------------------------------------------------------
# Linha de comando
# ---------------------------------------------------------------------------
def _escrever_github_output(meta: dict) -> None:
    destino = os.environ.get("GITHUB_OUTPUT")
    if not destino:
        return
    with open(destino, "a", encoding="utf-8") as f:
        for chave in ("ultima_atualizacao", "total", "novos", "removidos"):
            f.write(f"{chave}={meta[chave]}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Catálogo local de modelos do Compras Paraguai.")
    sub = parser.add_subparsers(dest="comando", required=True)
    p_at = sub.add_parser("atualizar", help="baixa o sitemap e atualiza data/catalogo_modelos.csv")
    p_at.add_argument("--max-sitemaps", type=int, default=None, help="limita quantos sitemaps baixar")
    p_at.add_argument("--navegador", action="store_true",
                      help="baixa pelo Chromium visível; você resolve a verificação anti-robô do site")
    p_su = sub.add_parser("sugerir", help="busca no catálogo local (sem internet)")
    p_su.add_argument("texto")
    p_su.add_argument("--limite", type=int, default=10)
    args = parser.parse_args(argv)

    if args.comando == "atualizar":
        cliente = None
        if args.navegador:
            from .sources.navegador import ClienteNavegador
            cliente = ClienteNavegador()
        try:
            meta = atualizar_catalogo(cliente=cliente, max_sitemaps=args.max_sitemaps)
        except ErroCatalogo as e:
            print(f"::error::Atualização do catálogo falhou: {e}", file=sys.stderr)
            return 1
        finally:
            if cliente is not None:
                cliente.fechar()
        print(f"Catálogo atualizado em {meta['ultima_atualizacao']}: {meta['total']} modelos "
              f"({meta['novos']} novos, {meta['removidos']} removidos).")
        _escrever_github_output(meta)
        return 0

    df = sugerir_modelos(args.texto, args.limite)
    if df.empty:
        print("Nenhum modelo encontrado no catálogo local.")
    for r in df.itertuples():
        print(f"{r.nome}  ->  {r.url}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
