"""Coleta real de ofertas no Compras Paraguai (https://www.comprasparaguai.com.br)."""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd

from .. import config, esquema
from ..predio import extrair_predio
from ..texto import dentro_de_cde, eh_ciudad_del_este
from . import parser_cp
from .base import FonteDeOfertas
from .http import ClienteHTTP

log = logging.getLogger(__name__)


@dataclass
class ResultadoColeta:
    lojas: pd.DataFrame
    produtos: pd.DataFrame
    ofertas: pd.DataFrame
    #: Uma linha por oferta descartada: data, termo, url_modelo, loja_slug, cidade, motivo.
    descartes: pd.DataFrame
    avisos: list[str] = field(default_factory=list)

    @property
    def descartadas_por_cidade(self) -> dict[str, int]:
        if self.descartes.empty:
            return {}
        return self.descartes["cidade"].fillna("não identificada").value_counts().to_dict()


def id_loja(slug: str) -> str:
    return f"CP-{slug}"


def id_produto(modelo_id: str) -> str:
    return f"CP-{modelo_id}"


class FonteComprasParaguai(FonteDeOfertas):
    """Coleta sob demanda: só os modelos dos termos (ou URLs) pedidos.

    Exemplo::

        fonte = FonteComprasParaguai(termos=["playstation 5 pro"])
        ofertas = fonte.carregar_ofertas()
    """

    nome = config.FONTE_CP

    def __init__(
        self,
        termos: list[str] | tuple[str, ...] = (),
        urls_modelos: list[str] | tuple[str, ...] = (),
        max_modelos_por_termo: int = 1,
        categoria: str | None = None,
        cliente: ClienteHTTP | None = None,
        dir_cache_lojas: str | Path | None = None,
        hoje: dt.date | None = None,
    ):
        self.termos = list(termos)
        self.urls_modelos = list(urls_modelos)
        self.max_modelos_por_termo = max_modelos_por_termo
        self.categoria = categoria
        self.hoje = hoje or dt.date.today()
        self.cliente = cliente or ClienteHTTP(hoje=self.hoje)
        self.dir_cache_lojas = Path(dir_cache_lojas or config.DIR_CACHE / "lojas")
        self._resultado: ResultadoColeta | None = None

    # -- a) busca ------------------------------------------------------------
    def buscar_modelos(self, termo: str) -> list[dict]:
        url = f"{config.URL_BASE_CP}/busca/?q={quote_plus(termo)}"
        return parser_cp.parse_busca(self.cliente.get(url))

    # -- b) página do modelo ---------------------------------------------------
    def coletar_ofertas(self, url_modelo: str) -> dict:
        return parser_cp.parse_modelo(self.cliente.get(url_modelo), url_modelo)

    # -- c) página da loja (cache permanente em disco) -------------------------
    def dados_loja(self, slug: str) -> dict:
        arquivo = self.dir_cache_lojas / f"{slug}.json"
        if arquivo.exists():
            return json.loads(arquivo.read_text(encoding="utf-8"))
        dados = parser_cp.parse_loja(self.cliente.get(f"{config.URL_BASE_CP}/lojas/{slug}/"), slug)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return dados

    # -- fluxo completo ----------------------------------------------------------
    def _urls_a_coletar(self) -> list[tuple[str | None, str]]:
        urls: list[tuple[str | None, str]] = [(None, u) for u in self.urls_modelos]
        for termo in self.termos:
            modelos = self.buscar_modelos(termo)
            if not modelos:
                log.warning("Nenhum modelo encontrado para '%s'.", termo)
                continue
            for m in modelos[: self.max_modelos_por_termo]:
                log.info("Termo '%s' -> modelo '%s' (%s)", termo, m["nome"], m["url"])
                urls.append((termo, m["url"]))
        return urls

    def coletar(self) -> ResultadoColeta:
        if self._resultado is not None:
            return self._resultado
        data = self.hoje.isoformat()
        lojas: dict[str, dict] = {}
        produtos: list[dict] = []
        ofertas: list[dict] = []
        descartes: list[dict] = []
        avisos: list[str] = []

        for termo, url in self._urls_a_coletar():
            modelo = self.coletar_ofertas(url)
            m = parser_cp.RE_URL_MODELO.match(parser_cp._caminho(url))
            produto_id = id_produto(m.group("id") if m else url)
            mantidas = 0
            for of in modelo["ofertas"]:
                slug = of["loja_slug"]
                cidade = of["cidade"]
                if parser_cp.oferta_fora_de_cde(cidade):
                    # A cidade já aparece na oferta: nem acessamos a página da loja.
                    descartes.append({"data": data, "termo": termo, "url_modelo": url,
                                      "loja_slug": slug, "cidade": cidade, "motivo": "cidade"})
                    continue
                if slug not in lojas:
                    lojas[slug] = self._montar_loja(slug, avisos)
                loja = lojas[slug]
                if loja is None:
                    descartes.append({"data": data, "termo": termo, "url_modelo": url, "loja_slug": slug,
                                      "cidade": self.dados_loja(slug).get("cidade"), "motivo": "cidade"})
                    continue
                ofertas.append({
                    "loja_id": loja["loja_id"],
                    "produto_id": produto_id,
                    "titulo_oferta": of["titulo_oferta"],
                    "codigo_loja": of["codigo_loja"],
                    "preco_usd": of["preco_usd"],
                    "preco_brl": of["preco_brl"],
                    "data_coleta": data,
                    "fonte": self.nome,
                    "tipo_dado": "real",
                })
                mantidas += 1
            if mantidas == 0:
                avisos.append(f"Modelo '{modelo['nome']}' ignorado: nenhuma oferta em Ciudad del Este.")
                continue
            produtos.append({
                "produto_id": produto_id,
                "nome": modelo["nome"],
                "categoria": self.categoria or modelo["categoria"],
                "url_modelo": url,
                "peso_kg": modelo["peso_kg"],
                "volume_l": modelo["volume_l"],
                "desconto_brasil_pct": modelo.get("desconto_brasil_pct"),
                "tipo_dado": "real",
            })

        resultado = ResultadoColeta(
            lojas=esquema.padronizar(pd.DataFrame([l for l in lojas.values() if l], columns=esquema.COLUNAS["lojas"]), "lojas"),
            produtos=esquema.padronizar(pd.DataFrame(produtos, columns=esquema.COLUNAS["produtos"]), "produtos"),
            ofertas=esquema.padronizar(pd.DataFrame(ofertas, columns=esquema.COLUNAS["ofertas"]), "ofertas"),
            descartes=pd.DataFrame(descartes, columns=["data", "termo", "url_modelo", "loja_slug", "cidade", "motivo"]),
            avisos=avisos,
        )
        por_cidade = resultado.descartadas_por_cidade
        log.info(
            "Coleta: %d ofertas mantidas em Ciudad del Este; %d descartadas por cidade %s.",
            len(resultado.ofertas), len(resultado.descartes), por_cidade or "",
        )
        for aviso in avisos:
            log.warning(aviso)
        self._resultado = resultado
        return resultado

    def _montar_loja(self, slug: str, avisos: list[str]) -> dict | None:
        """Linha da tabela ``lojas`` ou ``None`` se a loja não for de Ciudad del Este."""
        dados = self.dados_loja(slug)
        lat, lon = dados.get("latitude"), dados.get("longitude")
        cidade = dados.get("cidade")
        if cidade is None and lat is not None and dentro_de_cde(lat, lon):
            cidade = config.CIDADE_ALVO  # sem cidade escrita, mas o mapa está em CDE
        if not eh_ciudad_del_este(cidade):
            return None
        if lat is not None and not dentro_de_cde(lat, lon):
            avisos.append(f"Loja '{slug}': coordenadas ({lat}, {lon}) fora de Ciudad del Este; marcadas como pendentes.")
            lat = lon = None
        return {
            "loja_id": id_loja(slug),
            "nome": dados.get("nome"),
            "slug": slug,
            "cidade": config.CIDADE_ALVO,
            "endereco": dados.get("endereco"),
            "predio": extrair_predio(dados.get("endereco")),
            "latitude": lat,
            "longitude": lon,
            "coordenada_pendente": lat is None or lon is None,
            "abre": dados.get("abre"),
            "fecha": dados.get("fecha"),
            "tempo_permanencia_min": None,
            "fonte": self.nome,
            "tipo_dado": "real",
        }

    # -- interface FonteDeOfertas -------------------------------------------------
    def carregar_lojas(self) -> pd.DataFrame:
        return self.coletar().lojas

    def carregar_produtos(self) -> pd.DataFrame:
        return self.coletar().produtos

    def carregar_ofertas(self) -> pd.DataFrame:
        return self.coletar().ofertas
