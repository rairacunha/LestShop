"""Cliente HTTP "educado": robots.txt, intervalo mínimo, User-Agent e cache diário."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .. import config

log = logging.getLogger(__name__)


class ErroColeta(RuntimeError):
    """Falha ao baixar uma página (site fora do ar, bloqueio, robots.txt...)."""


class ClienteHTTP:
    """Baixa páginas respeitando as regras de boa conduta da Fase 1.

    * consulta o robots.txt do host antes da primeira página e recusa URLs
      proibidas;
    * espera pelo menos ``intervalo`` segundos entre requisições ao mesmo host
      (ou o Crawl-delay do robots.txt, se for maior);
    * identifica o projeto no User-Agent;
    * guarda cada página em ``data/cache/paginas/<AAAA-MM-DD>/`` e não baixa
      de novo a mesma URL no mesmo dia.
    """

    # Compartilhado entre instâncias: o intervalo vale para o processo todo.
    _ultimo_acesso: dict[str, float] = {}

    def __init__(
        self,
        dir_cache: str | Path = config.DIR_CACHE,
        intervalo: float = config.INTERVALO_MIN_SEGUNDOS,
        user_agent: str = config.USER_AGENT,
        sessao: requests.Session | None = None,
        dormir=time.sleep,
        relogio=time.monotonic,
        hoje: dt.date | None = None,
        timeout: float = 30.0,
    ):
        self.dir_cache = Path(dir_cache)
        self.intervalo = intervalo
        self.user_agent = user_agent
        self.sessao = sessao or requests.Session()
        self.dormir = dormir
        self.relogio = relogio
        self.hoje = hoje or dt.date.today()
        self.timeout = timeout
        self._robots: dict[str, RobotFileParser | None] = {}
        self.requisicoes = 0

    # -- cache ------------------------------------------------------------
    def _arquivo_cache(self, url: str) -> Path:
        chave = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.dir_cache / "paginas" / self.hoje.isoformat() / chave

    # -- rede ---------------------------------------------------------------
    def _esperar(self, host: str, intervalo: float) -> None:
        ultimo = self._ultimo_acesso.get(host)
        if ultimo is not None:
            falta = intervalo - (self.relogio() - ultimo)
            if falta > 0:
                log.debug("Aguardando %.1f s antes de acessar %s", falta, host)
                self.dormir(falta)
        self._ultimo_acesso[host] = self.relogio()

    def _baixar(self, url: str, intervalo: float) -> requests.Response:
        host = urlsplit(url).netloc
        self._esperar(host, intervalo)
        self.requisicoes += 1
        try:
            resp = self.sessao.get(url, headers={"User-Agent": self.user_agent}, timeout=self.timeout)
        except requests.RequestException as e:
            motivo = "sem conexão (rede bloqueada ou site fora do ar)" if isinstance(e, requests.ConnectionError) else str(e)
            raise ErroColeta(f"Não foi possível acessar {url}: {motivo}.") from e
        return resp

    def _robots_de(self, url: str) -> RobotFileParser | None:
        partes = urlsplit(url)
        raiz = f"{partes.scheme}://{partes.netloc}"
        if raiz in self._robots:
            return self._robots[raiz]
        url_robots = raiz + "/robots.txt"
        cache = self._arquivo_cache(url_robots)
        if cache.exists():
            texto = cache.read_text(encoding="utf-8")
        else:
            resp = self._baixar(url_robots, self.intervalo)
            if resp.status_code in (401, 403):
                raise ErroColeta(f"O robots.txt de {raiz} negou acesso (HTTP {resp.status_code}); coleta interrompida.")
            texto = resp.text if resp.status_code == 200 else ""
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(texto, encoding="utf-8")
        rp = RobotFileParser()
        rp.parse(texto.splitlines())
        self._robots[raiz] = rp
        return rp

    def sitemaps_do_robots(self, url_site: str) -> list[str]:
        rp = self._robots_de(url_site)
        return list(rp.site_maps() or []) if rp else []

    def get_bytes(self, url: str) -> bytes:
        cache = self._arquivo_cache(url)
        if cache.exists():
            return cache.read_bytes()
        rp = self._robots_de(url)
        intervalo = self.intervalo
        if rp is not None:
            if not rp.can_fetch(self.user_agent, url):
                raise ErroColeta(f"O robots.txt proíbe acessar {url}; coleta interrompida.")
            atraso = rp.crawl_delay(self.user_agent)
            if atraso:
                intervalo = max(intervalo, float(atraso))
        resp = self._baixar(url, intervalo)
        if resp.status_code != 200:
            raise ErroColeta(f"O site respondeu HTTP {resp.status_code} para {url}.")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(resp.content)
        log.info("Baixado: %s", url)
        return resp.content

    def get(self, url: str) -> str:
        conteudo = self.get_bytes(url)
        try:
            return conteudo.decode("utf-8")
        except UnicodeDecodeError:
            return conteudo.decode("latin-1")
