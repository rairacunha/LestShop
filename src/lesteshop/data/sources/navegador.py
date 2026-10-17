"""Cliente que baixa páginas por um navegador real, com verificação feita por uma pessoa.

O Compras Paraguai usa proteção anti-robô (Cloudflare). O LesteShop não tenta
contornar essa proteção: abre uma janela visível do Chromium e, quando o site
pede verificação, **o usuário a resolve**. Depois disso, as páginas são
baixadas dentro da mesma janela (``fetch`` na própria página), com as mesmas
regras do :class:`ClienteHTTP`: robots.txt, 10 s entre requisições, cache diário.

Limites assumidos de propósito:

* nada de plugins "stealth", disfarce de impressão digital ou resolução
  automática de CAPTCHA;
* a liberação (cookie do Cloudflare) fica só neste navegador, no perfil salvo em
  ``data/cache/navegador/``; ela não é copiada para outro cliente;
* se a verificação não for resolvida dentro do prazo, a coleta para com erro.

Requer ``pip install playwright`` e ``playwright install chromium``.
"""

from __future__ import annotations

import base64
import logging
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from .. import config
from .http import ClienteHTTP, ErroColeta

log = logging.getLogger(__name__)

# Trechos que aparecem na página de desafio do Cloudflare.
_MARCAS_DESAFIO = ("/cdn-cgi/challenge-platform/", "challenges.cloudflare.com", "cf-chl-")
_TITULOS_DESAFIO = ("just a moment", "um momento", "attention required", "verificando", "checking your browser")

_JS_FETCH = """
async ([url, projeto]) => {
  const r = await fetch(url, {credentials: 'include', headers: {'X-Projeto-Academico': projeto}});
  const bytes = new Uint8Array(await r.arrayBuffer());
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return {status: r.status, cf: r.headers.get('cf-mitigated'), corpo: btoa(s)};
}
"""


class _Resposta:
    """Imita o pedaço de ``requests.Response`` que o ClienteHTTP usa."""

    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def _e_desafio(titulo: str, html: str) -> bool:
    return any(m in html for m in _MARCAS_DESAFIO) or any(t in titulo.lower() for t in _TITULOS_DESAFIO)


class ClienteNavegador(ClienteHTTP):
    """``ClienteHTTP`` em que cada download acontece dentro de um Chromium visível.

    Use como gerenciador de contexto para fechar o navegador no fim::

        with ClienteNavegador() as cliente:
            html = cliente.get("https://www.comprasparaguai.com.br/busca/?q=ps5")
    """

    def __init__(
        self,
        dir_perfil: str | Path | None = None,
        janela_visivel: bool = True,
        prazo_verificacao_s: float = 300.0,
        avisar=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.dir_perfil = Path(dir_perfil or self.dir_cache / "navegador")
        self.janela_visivel = janela_visivel
        self.prazo_verificacao_s = prazo_verificacao_s
        self.avisar = avisar or (lambda msg: print(msg, file=sys.stderr, flush=True))
        self._pw = None
        self._contexto = None
        self._pagina = None

    # -- ciclo de vida -------------------------------------------------------------
    def _abrir(self):
        if self._pagina is not None:
            return self._pagina
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise ErroColeta("Playwright não instalado. Rode: pip install playwright && playwright install chromium") from e
        self.dir_perfil.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        try:
            self._contexto = self._pw.chromium.launch_persistent_context(
                str(self.dir_perfil), headless=not self.janela_visivel, locale="pt-BR",
            )
        except Exception as e:
            self.fechar()
            raise ErroColeta(
                f"Não foi possível abrir o navegador ({e}). A coleta com verificação precisa de uma tela: "
                "rode no seu computador, não num servidor."
            ) from e
        self._pagina = self._contexto.pages[0] if self._contexto.pages else self._contexto.new_page()
        return self._pagina

    def fechar(self) -> None:
        if self._contexto is not None:
            try:
                self._contexto.close()
            except Exception:
                pass
        if self._pw is not None:
            self._pw.stop()
        self._pw = self._contexto = self._pagina = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fechar()

    # -- verificação humana ----------------------------------------------------------
    def _pagina_em_desafio(self) -> bool:
        p = self._pagina
        try:
            return _e_desafio(p.title(), p.content())
        except Exception:
            return True  # página navegando no meio do desafio

    def _aguardar_verificacao(self, url: str) -> None:
        """Abre ``url`` na janela e espera a pessoa resolver a verificação."""
        pagina = self._abrir()
        pagina.goto(url, wait_until="domcontentloaded", timeout=60_000)
        if not self._pagina_em_desafio():
            return
        self.avisar(
            "\n>>> O Compras Paraguai pediu uma verificação anti-robô.\n"
            ">>> Resolva-a na janela do navegador que abriu (marque a caixa, se houver) e aguarde.\n"
            f">>> Prazo: {int(self.prazo_verificacao_s // 60)} min.\n"
        )
        limite = time.monotonic() + self.prazo_verificacao_s
        while time.monotonic() < limite:
            time.sleep(2)
            if not self._pagina_em_desafio():
                self.avisar(">>> Verificação concluída. Continuando a coleta (10 s entre páginas)...\n")
                return
        raise ErroColeta("A verificação do site não foi resolvida no prazo; coleta interrompida sem gravar dados.")

    # -- download ---------------------------------------------------------------------
    def _baixar(self, url: str, intervalo: float):
        partes = urlsplit(url)
        origem = f"{partes.scheme}://{partes.netloc}"
        pagina = self._abrir()
        if not pagina.url.startswith(origem):
            # o fetch precisa partir de uma página do próprio site (mesma origem)
            self._esperar(partes.netloc, intervalo)
            self.requisicoes += 1
            self._aguardar_verificacao(origem + "/")
        for _tentativa in range(3):
            self._esperar(partes.netloc, intervalo)
            self.requisicoes += 1
            try:
                r = pagina.evaluate(_JS_FETCH, [url, config.USER_AGENT])
            except Exception as e:
                raise ErroColeta(f"Falha ao baixar {url} pelo navegador: {e}") from e
            if r["cf"] == "challenge":
                log.info("Verificação pedida ao acessar %s", url)
                self._aguardar_verificacao(url)
                continue
            return _Resposta(r["status"], base64.b64decode(r["corpo"]))
        raise ErroColeta(f"O site continuou pedindo verificação para {url}; coleta interrompida.")
