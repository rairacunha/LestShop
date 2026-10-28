"""Extração de dados das páginas do Compras Paraguai (sem acesso à rede).

As funções recebem o HTML já baixado e devolvem dicionários. Em vez de
depender de nomes de classes CSS (que mudam com frequência), a extração usa
os padrões estáveis do site:

* página de modelo: URL ``/<slug>_<id>/``;
* página de loja: URL ``/lojas/<slug>/``;
* preços com os prefixos ``US$`` e ``R$``.

Se a página não tiver o que se espera, é lançado :class:`ErroEstruturaHTML`
com uma mensagem em português; nunca devolvemos dados vazios ou inventados.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from .. import config
from ..texto import encontrar_cidades, eh_ciudad_del_este, parse_preco

RE_URL_MODELO = re.compile(r"^/(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)_(?P<id>\d+)/?$")
RE_URL_LOJA = re.compile(r"^/lojas/(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)/?$")
RE_USD = re.compile(r"US\$\s*([\d.,]+)")
RE_BRL = re.compile(r"R\$\s*([\d.,]+)")
RE_CODIGO = re.compile(r"C[óo]d(?:igo)?\.?(?:\s+(?:da\s+)?loja)?\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9\-./]*)", re.IGNORECASE)
RE_SEM_RESULTADO = re.compile(r"nenhum (?:produto|resultado)|n[ãa]o (?:encontramos|foram encontrad)", re.IGNORECASE)
RE_DESCONTO_BRASIL = re.compile(
    r"(?<![\d.,])(\d{1,2}(?:[.,]\d+)?)\s*%\s*mais\s+barato\s+(?:do\s+)?que\s+no\s+Brasil", re.IGNORECASE
)
RE_SEM_OFERTA = re.compile(r"(?:sem|nenhuma) ofertas?|indispon[íi]vel no momento", re.IGNORECASE)


class ErroEstruturaHTML(RuntimeError):
    """A página não tem a estrutura esperada (o site provavelmente mudou)."""


def _sopa(html: str) -> BeautifulSoup:
    sopa = BeautifulSoup(html, "lxml")
    for t in sopa(["script", "style", "noscript", "template"]):
        if t.name == "script" and t.get("type") == "application/ld+json":
            continue
        t.decompose()
    return sopa


def _conteudo_principal(sopa: BeautifulSoup) -> Tag:
    """Remove cabeçalho, rodapé e menus (que citam várias cidades)."""
    for t in sopa.find_all(["header", "footer", "nav"]):
        t.decompose()
    return sopa.find("main") or sopa.body or sopa


def _texto(no: Tag) -> str:
    return re.sub(r"\s+", " ", no.get_text(" ", strip=True)).strip()


def _caminho(href: str) -> str:
    return urlsplit(urljoin(config.URL_BASE_CP + "/", href)).path


def _cartao(ancora: Tag, padrao: re.Pattern, chave_propria: str, marcador: re.Pattern = RE_USD) -> Tag | None:
    """Sobe a partir de ``ancora`` até o menor ancestral que contém um preço US$
    sem incluir links para outro item do mesmo tipo (outro modelo/outra loja)."""
    no = ancora
    while no.parent is not None and no.parent.name not in ("body", "html", "[document]"):
        no = no.parent
        outros = {
            m.group("slug") + (m.groupdict().get("id") or "")
            for a in no.find_all("a", href=True)
            if (m := padrao.match(_caminho(a["href"])))
        }
        if outros - {chave_propria}:
            return None
        if marcador.search(_texto(no)):
            return no
    return None


def _json_ld(sopa: BeautifulSoup) -> list[dict]:
    blocos = []
    for s in sopa.find_all("script", type="application/ld+json"):
        try:
            dado = json.loads(s.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        itens = dado if isinstance(dado, list) else dado.get("@graph", [dado]) if isinstance(dado, dict) else []
        blocos.extend(i for i in itens if isinstance(i, dict))
    return blocos


# ---------------------------------------------------------------------------
# a) Página de busca
# ---------------------------------------------------------------------------
def parse_busca(html: str) -> list[dict]:
    """Lista de modelos: ``nome``, ``url``, ``modelo_id``, ``preco_a_partir_usd``."""
    sopa = _sopa(html)
    principal = _conteudo_principal(sopa)
    modelos: dict[str, dict] = {}
    for a in principal.find_all("a", href=True):
        caminho = _caminho(a["href"])
        m = RE_URL_MODELO.match(caminho)
        if not m:
            continue
        chave = m.group("slug") + m.group("id")
        item = modelos.setdefault(chave, {
            "nome": None,
            "url": config.URL_BASE_CP + caminho.rstrip("/") + "/",
            "modelo_id": m.group("id"),
            "slug": m.group("slug"),
            "preco_a_partir_usd": None,
        })
        nome = (a.get("title") or _texto(a) or "").strip()
        if nome and not RE_USD.search(nome) and len(nome) > len(item["nome"] or ""):
            item["nome"] = nome
        if item["preco_a_partir_usd"] is None:
            cartao = _cartao(a, RE_URL_MODELO, chave)
            if cartao is not None:
                item["preco_a_partir_usd"] = parse_preco(RE_USD.search(_texto(cartao)).group(1))
    if not modelos:
        if RE_SEM_RESULTADO.search(_texto(principal)):
            return []
        raise ErroEstruturaHTML(
            "Página de busca do Compras Paraguai sem nenhum link de modelo (/<slug>_<id>/) "
            "e sem aviso de 'nenhum resultado'. O HTML do site provavelmente mudou; "
            "revise lesteshop/data/sources/parser_cp.py."
        )
    return list(modelos.values())


# ---------------------------------------------------------------------------
# b) Página de modelo
# ---------------------------------------------------------------------------
def _especificacoes(principal: Tag) -> dict[str, str]:
    specs: dict[str, str] = {}
    for tr in principal.find_all("tr"):
        celulas = tr.find_all(["th", "td"])
        if len(celulas) >= 2:
            specs[_texto(celulas[0]).rstrip(":")] = _texto(celulas[1])
    for dt_ in principal.find_all("dt"):
        dd = dt_.find_next_sibling("dd")
        if dd is not None:
            specs[_texto(dt_).rstrip(":")] = _texto(dd)
    return specs


def converter_peso_kg(texto: str | None) -> float | None:
    if not texto:
        return None
    m = re.search(r"([\d.,]+)\s*(kg|quilo|g|gr|gramas|lb|lbs)\b", texto, re.IGNORECASE)
    if not m:
        return None
    valor = parse_preco(m.group(1))
    if valor is None or valor <= 0:
        return None
    unidade = m.group(2).lower()
    if unidade.startswith("kg") or unidade.startswith("quilo"):
        return round(valor, 4)
    if unidade.startswith("lb"):
        return round(valor * 0.45359237, 4)
    return round(valor / 1000, 4)


def converter_volume_l(texto: str | None) -> float | None:
    """'47 x 38 x 15 cm' -> 26.79 litros. Exige três medidas e a unidade."""
    if not texto:
        return None
    m = re.search(
        r"([\d.,]+)\s*(?:cm|mm|m)?\s*[x×]\s*([\d.,]+)\s*(?:cm|mm|m)?\s*[x×]\s*([\d.,]+)\s*(cm|mm|m)\b",
        texto, re.IGNORECASE,
    )
    if not m:
        return None
    medidas = [parse_preco(m.group(i)) for i in (1, 2, 3)]
    if any(v is None or v <= 0 for v in medidas):
        return None
    fator = {"mm": 0.1, "cm": 1.0, "m": 100.0}[m.group(4).lower()]
    a, b, c = (v * fator for v in medidas)
    return round(a * b * c / 1000, 3)


def extrair_desconto_brasil(texto: str) -> float | None:
    """'~28% mais barato que no Brasil' -> 0.28. Sem o aviso na página -> None (nunca estimado)."""
    m = RE_DESCONTO_BRASIL.search(texto or "")
    if not m:
        return None
    valor = parse_preco(m.group(1))
    if valor is None or not 0 <= valor < 100:
        return None
    return round(valor / 100, 4)


def _valor_spec(specs: dict[str, str], *chaves: str, preferir: str | None = None) -> str | None:
    candidatos = [(k, v) for k, v in specs.items() if all(c in k.lower() for c in chaves)]
    if preferir:
        candidatos.sort(key=lambda kv: preferir not in kv[0].lower())
    return candidatos[0][1] if candidatos else None


_CLASSES_TITULO = re.compile(r"titul|title|nome|name|descri", re.IGNORECASE)


def _titulo_oferta(cartao: Tag, nome_loja: str) -> str | None:
    for no in cartao.find_all(True):
        classes = " ".join(no.get("class", []))
        if _CLASSES_TITULO.search(classes) and not no.find("a", href=RE_URL_LOJA_HREF):
            t = _texto(no)
            if t and t != nome_loja and not RE_USD.search(t):
                return t
    # Fallback: maior trecho de texto que não é preço, código nem nome da loja.
    trechos = [s.strip() for s in cartao.stripped_strings]
    trechos = [s for s in trechos if s != nome_loja and not RE_USD.search(s) and not RE_BRL.search(s)
               and not RE_CODIGO.match(s) and not encontrar_cidades(s) and len(s) > 8]
    return max(trechos, key=len) if trechos else None


RE_URL_LOJA_HREF = re.compile(r"/lojas/[a-z0-9-]+/?$")


def parse_modelo(html: str, url_modelo: str) -> dict:
    """Dados do modelo e lista de ofertas.

    Cada oferta: ``loja_slug``, ``loja_nome``, ``titulo_oferta``,
    ``codigo_loja``, ``preco_usd``, ``preco_brl`` e ``cidade`` (se aparecer).
    """
    sopa = _sopa(html)
    principal = _conteudo_principal(sopa)
    h1 = principal.find("h1")
    if h1 is None or not _texto(h1):
        raise ErroEstruturaHTML(
            f"Página de modelo sem título <h1>: {url_modelo}. O HTML do Compras Paraguai "
            "provavelmente mudou; revise lesteshop/data/sources/parser_cp.py."
        )
    nome = _texto(h1)

    categoria = None
    trilha = principal.select("[class*=breadcrumb] a, nav[aria-label*=readcrumb] a, ol.breadcrumb li")
    nomes_trilha = [_texto(t) for t in trilha if _texto(t) and _texto(t).lower() not in {"home", "início", "inicio"}]
    if nomes_trilha:
        categoria = nomes_trilha[-1] if nomes_trilha[-1] != nome else (nomes_trilha[-2] if len(nomes_trilha) > 1 else None)

    specs = _especificacoes(principal)
    peso_kg = converter_peso_kg(_valor_spec(specs, "peso", "bruto"))
    volume_l = converter_volume_l(_valor_spec(specs, "dimens", preferir="embalagem"))
    desconto_brasil_pct = extrair_desconto_brasil(_texto(principal))

    ofertas = []
    vistos: set[int] = set()
    for a in principal.find_all("a", href=True):
        m = RE_URL_LOJA.match(_caminho(a["href"]))
        if not m:
            continue
        slug = m.group("slug")
        cartao = _cartao(a, RE_URL_LOJA, slug)
        if cartao is None or id(cartao) in vistos:
            continue
        vistos.add(id(cartao))
        texto = _texto(cartao)
        preco_usd = parse_preco(RE_USD.search(texto).group(1))
        if preco_usd is None or preco_usd <= 0:
            raise ErroEstruturaHTML(
                f"Preço em US$ ilegível na oferta da loja '{slug}' em {url_modelo}: '{texto[:120]}'."
            )
        brl = RE_BRL.search(texto)
        codigo = RE_CODIGO.search(texto)
        nomes_loja = [_texto(x) for x in cartao.find_all("a", href=True)
                      if RE_URL_LOJA.match(_caminho(x["href"])) and _texto(x)]
        nome_loja = (a.get("title") or (nomes_loja[0] if nomes_loja else "") or "").strip()
        cidades = encontrar_cidades(texto)
        ofertas.append({
            "loja_slug": slug,
            "loja_nome": nome_loja or None,
            "titulo_oferta": _titulo_oferta(cartao, nome_loja),
            "codigo_loja": codigo.group(1) if codigo else None,
            "preco_usd": preco_usd,
            "preco_brl": parse_preco(brl.group(1)) if brl else None,
            "cidade": cidades[0] if cidades else None,
        })

    if not ofertas and not RE_SEM_OFERTA.search(_texto(principal)):
        raise ErroEstruturaHTML(
            f"Nenhuma oferta encontrada em {url_modelo} (esperava links /lojas/<slug>/ junto a preços "
            "em US$). O HTML do Compras Paraguai provavelmente mudou; revise "
            "lesteshop/data/sources/parser_cp.py antes de gravar qualquer dado."
        )
    return {
        "nome": nome,
        "categoria": categoria,
        "url_modelo": url_modelo,
        "peso_kg": peso_kg,
        "volume_l": volume_l,
        "desconto_brasil_pct": desconto_brasil_pct,
        "ofertas": ofertas,
    }


# ---------------------------------------------------------------------------
# c) Página de loja
# ---------------------------------------------------------------------------
_RE_COORD = [
    re.compile(r"[?&](?:q|ll|center|query|destination|daddr)=(-?\d{1,2}\.\d+)\s*(?:,|%2C)\s*(-?\d{1,3}\.\d+)"),
    re.compile(r"@(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)"),
    re.compile(r"!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)"),
]
_RE_HORARIO = re.compile(
    r"(\d{1,2})(?:[:h](\d{2}))?\s*h?\s*(?:às|as|a|-|–|até)\s*(\d{1,2})(?:[:h](\d{2}))?\s*h?", re.IGNORECASE
)


def _coordenada_plausivel(lat: float, lon: float) -> bool:
    # Paraguai: latitude entre -28 e -19, longitude entre -63 e -54.
    return -28 <= lat <= -19 and -63 <= lon <= -54


def _extrair_coordenadas(principal: Tag, ld: list[dict]) -> tuple[float | None, float | None]:
    for item in ld:
        geo = item.get("geo") if isinstance(item.get("geo"), dict) else None
        if geo and "latitude" in geo and "longitude" in geo:
            try:
                lat, lon = float(geo["latitude"]), float(geo["longitude"])
            except (TypeError, ValueError):
                continue
            if _coordenada_plausivel(lat, lon):
                return lat, lon
    for no in principal.find_all(True):
        attrs = {k.lower(): v for k, v in no.attrs.items() if isinstance(v, str)}
        lat = attrs.get("data-lat") or attrs.get("data-latitude")
        lon = attrs.get("data-lng") or attrs.get("data-lon") or attrs.get("data-longitude")
        if lat and lon:
            try:
                if _coordenada_plausivel(float(lat), float(lon)):
                    return float(lat), float(lon)
            except ValueError:
                pass
        for chave in ("src", "href", "data-src"):
            valor = attrs.get(chave)
            if valor and ("google" in valor or "maps" in valor or "osm" in valor):
                for padrao in _RE_COORD:
                    m = padrao.search(valor)
                    if m and _coordenada_plausivel(float(m.group(1)), float(m.group(2))):
                        return float(m.group(1)), float(m.group(2))
    return None, None


def _extrair_endereco(principal: Tag, ld: list[dict]) -> str | None:
    for item in ld:
        end = item.get("address")
        if isinstance(end, dict):
            partes = [end.get(k) for k in ("streetAddress", "addressLocality", "addressRegion")]
            texto = ", ".join(p for p in partes if p)
            if texto:
                return texto
        elif isinstance(end, str) and end.strip():
            return end.strip()
    no = principal.find("address") or principal.select_one("[class*=endereco], [class*=address], [itemprop=address]")
    if no is not None and _texto(no):
        return re.sub(r"^Endere[çc]o\s*:?\s*", "", _texto(no), flags=re.IGNORECASE)
    rotulo = principal.find(string=re.compile(r"Endere[çc]o|Direcci[óo]n", re.IGNORECASE))
    if rotulo is not None:
        bloco = rotulo.parent
        texto = re.sub(r"^.*?(?:Endere[çc]o|Direcci[óo]n)\s*:?\s*", "", _texto(bloco), flags=re.IGNORECASE)
        if not texto:
            irmao = bloco.find_next_sibling()
            texto = _texto(irmao) if irmao is not None else ""
        return texto or None
    return None


def _extrair_horario(principal: Tag) -> tuple[str | None, str | None]:
    rotulo = principal.find(string=re.compile(r"Hor[áa]rio", re.IGNORECASE))
    if rotulo is None:
        return None, None
    bloco = rotulo.parent
    texto = _texto(bloco.parent if len(_texto(bloco)) < 15 and bloco.parent is not None else bloco)
    m = _RE_HORARIO.search(texto.split("Hor", 1)[-1])
    if not m:
        return None, None
    h1, m1, h2, m2 = m.group(1), m.group(2) or "00", m.group(3), m.group(4) or "00"
    if int(h1) > 23 or int(h2) > 23:
        return None, None
    return f"{int(h1):02d}:{m1}", f"{int(h2):02d}:{m2}"


def parse_loja(html: str, slug: str) -> dict:
    """Nome, cidade, endereço, latitude/longitude (se houver mapa) e horário."""
    sopa = _sopa(html)
    ld = _json_ld(sopa)
    principal = _conteudo_principal(sopa)
    h1 = principal.find("h1")
    if h1 is None or not _texto(h1):
        raise ErroEstruturaHTML(
            f"Página da loja '{slug}' sem título <h1>. O HTML do Compras Paraguai provavelmente "
            "mudou; revise lesteshop/data/sources/parser_cp.py."
        )
    endereco = _extrair_endereco(principal, ld)
    lat, lon = _extrair_coordenadas(principal, ld)
    cidades_end = encontrar_cidades(endereco or "")
    cidades_pag = encontrar_cidades(_texto(principal))
    if cidades_end:
        cidade = cidades_end[-1]
    elif len(set(cidades_pag)) == 1:
        cidade = cidades_pag[0]
    else:
        cidade = None
    abre, fecha = _extrair_horario(principal)
    return {
        "slug": slug,
        "nome": _texto(h1),
        "cidade": cidade,
        "endereco": endereco,
        "latitude": lat,
        "longitude": lon,
        "abre": abre,
        "fecha": fecha,
    }


def oferta_fora_de_cde(cidade: str | None) -> bool:
    """True quando a cidade é conhecida e não é Ciudad del Este."""
    return cidade is not None and not eh_ciudad_del_este(cidade)
