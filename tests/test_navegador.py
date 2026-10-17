"""ClienteNavegador contra um servidor local que imita a verificação do Cloudflare.

O "usuário" é simulado pelo teste clicando no botão da página de desafio.
Pulado se o Playwright/Chromium não estiver disponível.
"""

import datetime as dt
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("playwright.sync_api")

from lesteshop.data.sources.http import ClienteHTTP, ErroColeta  # noqa: E402
from lesteshop.data.sources.navegador import ClienteNavegador  # noqa: E402

DESAFIO = b"""<html><head><title>Just a moment...</title></head><body>
<script src="/cdn-cgi/challenge-platform/h/b/orchestrate/x.js"></script>
<button id="sou-humano" onclick="document.cookie='liberado=1; path=/'; location.reload()">Verificar</button>
</body></html>"""


class Servidor(BaseHTTPRequestHandler):
    acessos: list[tuple[str, str]] = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        Servidor.acessos.append((self.path, self.headers.get("X-Projeto-Academico", "")))
        if "liberado=1" not in (self.headers.get("Cookie") or ""):
            self.send_response(403)
            self.send_header("cf-mitigated", "challenge")
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DESAFIO)
            return
        corpo = {"/robots.txt": b"User-agent: *\nDisallow: /proibido/\n",
                 "/": b"<html><head><title>Inicio</title></head><body>ok</body></html>",
                 "/pagina/": "<html><body><h1>Página real ção</h1></body></html>".encode()}.get(self.path)
        self.send_response(200 if corpo else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo or b"nao encontrado")


@pytest.fixture
def servidor():
    Servidor.acessos = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Servidor)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _cliente(tmp_path, avisar):
    ClienteHTTP._ultimo_acesso.clear()
    try:
        c = ClienteNavegador(dir_perfil=tmp_path / "perfil", janela_visivel=False, prazo_verificacao_s=20,
                             avisar=avisar, dir_cache=tmp_path / "cache", intervalo=0.2,
                             hoje=dt.date(2026, 10, 17))
        c._abrir()
    except ErroColeta as e:
        pytest.skip(f"Chromium indisponível: {e}")
    return c


def test_pessoa_resolve_verificacao_e_coleta_continua(servidor, tmp_path):
    mensagens = []

    def pessoa(msg):  # simula o usuário clicando na janela
        mensagens.append(msg)
        if "pediu uma verificação" in msg:
            cliente._pagina.click("#sou-humano")

    cliente = _cliente(tmp_path, pessoa)
    try:
        html = cliente.get(servidor + "/pagina/")
        assert "Página real ção" in html
        assert any("pediu uma verificação" in m for m in mensagens)
        assert any("Verificação concluída" in m for m in mensagens)
        # robots.txt foi lido e respeitado
        with pytest.raises(ErroColeta, match="robots.txt proíbe"):
            cliente.get(servidor + "/proibido/x")
        # o projeto se identifica nas requisições feitas pela página
        assert any(h.startswith("LesteShop") for p, h in Servidor.acessos if p == "/pagina/")
        # cache: a mesma página no mesmo dia não gera novo acesso
        n = len(Servidor.acessos)
        cliente.get(servidor + "/pagina/")
        assert len(Servidor.acessos) == n
    finally:
        cliente.fechar()


def test_verificacao_nao_resolvida_interrompe(servidor, tmp_path):
    cliente = _cliente(tmp_path, lambda msg: None)
    cliente.prazo_verificacao_s = 3
    try:
        with pytest.raises(ErroColeta, match="não foi resolvida no prazo"):
            cliente.get(servidor + "/pagina/")
    finally:
        cliente.fechar()
