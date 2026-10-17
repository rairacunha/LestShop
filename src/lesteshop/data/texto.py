"""Funções de texto: normalização, preços, nomes a partir de slugs e cidades."""

from __future__ import annotations

import re
import unicodedata

from . import config

# Cidades paraguaias que aparecem no Compras Paraguai. Só Ciudad del Este
# interessa; as demais servem para reconhecer (e descartar) ofertas.
CIDADES_CONHECIDAS = (
    "Ciudad del Este",
    "Salto del Guairá",
    "Pedro Juan Caballero",
    "Encarnación",
    "Asunción",
    "Hernandarias",
    "Presidente Franco",
    "Minga Guazú",
    "Capitán Bado",
    "Bella Vista",
)
_SINONIMOS_CDE = {"ciudad del este", "cidade do leste", "cde"}


def remover_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def normalizar(texto: object) -> str:
    """Minúsculas, sem acentos, só letras/dígitos separados por um espaço."""
    if texto is None:
        return ""
    texto = remover_acentos(str(texto)).lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return texto.strip()


def tokens(texto: object) -> list[str]:
    return normalizar(texto).split()


def eh_ciudad_del_este(cidade: object) -> bool:
    return normalizar(cidade) in _SINONIMOS_CDE


def encontrar_cidades(texto: str) -> list[str]:
    """Cidades conhecidas mencionadas no texto, na ordem em que aparecem."""
    alvo = f" {normalizar(texto)} "
    achadas = []
    for cidade in CIDADES_CONHECIDAS:
        pos = alvo.find(f" {normalizar(cidade)} ")
        if pos >= 0:
            achadas.append((pos, cidade))
    return [c for _, c in sorted(achadas)]


_RE_NUMERO = re.compile(r"\d[\d.,]*")


def parse_preco(texto: object) -> float | None:
    """Converte '1.234,56', '1,234.56', '689,00' ou '689' em float.

    Regra para separadores: com '.' e ',' o último é o decimal; com só um
    deles, é decimal quando seguido de 1 ou 2 dígitos no fim, senão milhar.
    """
    if texto is None:
        return None
    m = _RE_NUMERO.search(str(texto))
    if not m:
        return None
    num = m.group(0).rstrip(".,")
    if "," in num and "." in num:
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "," in num or "." in num:
        sep = "," if "," in num else "."
        inteiro, _, frac = num.rpartition(sep)
        if len(frac) in (1, 2) and num.count(sep) == 1:
            num = inteiro + "." + frac
        else:
            num = num.replace(sep, "")
    try:
        return float(num)
    except ValueError:
        return None


_SIGLAS = {"tb", "gb", "mb", "hd", "ssd", "usb", "led", "oled", "qled", "uhd", "fhd",
           "ps5", "ps4", "jbl", "lg", "tv", "rgb", "edt", "edp", "ml", "nfc", "dji"}


def nome_de_slug(slug: str) -> str:
    """'sony-playstation-5-pro-2tb-digital-edition' -> 'Sony Playstation 5 Pro 2TB Digital Edition'."""
    partes = []
    for p in slug.strip("/").split("-"):
        if not p:
            continue
        if p in _SIGLAS or re.fullmatch(r"\d+(tb|gb|mb|k)", p):
            partes.append(p.upper())
        elif p[0].isdigit():
            partes.append(p)
        else:
            partes.append(p.capitalize())
    return " ".join(partes)


def dentro_de_cde(lat: object, lon: object) -> bool:
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return (config.CDE_LAT_MIN <= lat_f <= config.CDE_LAT_MAX
            and config.CDE_LON_MIN <= lon_f <= config.CDE_LON_MAX)
