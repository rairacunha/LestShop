"""Baixa páginas reais do Compras Paraguai para tests/fixtures/reais/.

Serve para conferir o parser contra o HTML real (as fixtures padrão foram
escritas à mão). Segue as mesmas regras de boa conduta da coleta.

    python -m lesteshop.data.salvar_fixtures "playstation 5 pro" --navegador
"""

from __future__ import annotations

import argparse
import logging
from urllib.parse import quote_plus

from . import config
from .sources import parser_cp
from .sources.http import ClienteHTTP
from .sources.navegador import ClienteNavegador

DESTINO = config.RAIZ / "tests" / "fixtures" / "reais"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("termo")
    parser.add_argument("--max-lojas", type=int, default=3)
    parser.add_argument("--navegador", action="store_true",
                        help="baixa pelo Chromium visível; você resolve a verificação anti-robô do site")
    args = parser.parse_args(argv)
    cliente = ClienteNavegador() if args.navegador else ClienteHTTP()
    try:
        return _salvar(args, cliente)
    finally:
        if args.navegador:
            cliente.fechar()


def _salvar(args, cliente) -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)

    html_busca = cliente.get(f"{config.URL_BASE_CP}/busca/?q={quote_plus(args.termo)}")
    (DESTINO / "busca.html").write_text(html_busca, encoding="utf-8")
    modelos = parser_cp.parse_busca(html_busca)
    if not modelos:
        print("A busca não retornou modelos.")
        return 1
    url = modelos[0]["url"]
    html_modelo = cliente.get(url)
    (DESTINO / "modelo.html").write_text(html_modelo, encoding="utf-8")
    (DESTINO / "modelo_url.txt").write_text(url + "\n", encoding="utf-8")
    slugs = list(dict.fromkeys(o["loja_slug"] for o in parser_cp.parse_modelo(html_modelo, url)["ofertas"]))
    for slug in slugs[: args.max_lojas]:
        html = cliente.get(f"{config.URL_BASE_CP}/lojas/{slug}/")
        (DESTINO / f"loja_{slug}.html").write_text(html, encoding="utf-8")
    print(f"Páginas salvas em {DESTINO} ({cliente.requisicoes} requisições).")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
