"""Identifica o shopping/galeria/edifício a partir do endereço da loja.

Lojas no mesmo prédio terão deslocamento quase zero na Fase 2, por isso o
nome é normalizado (ex.: "SHOPPING PARIS", "Shop. Paris" -> "Shopping Paris").
"""

from __future__ import annotations

import re

from .texto import normalizar

# Prefixos que indicam um prédio comercial, com a forma canônica.
_PREFIXOS = [
    (r"shopping|shop\.?|s\.?c\.?", "Shopping"),
    (r"centro comercial|c\.?c\.?", "Centro Comercial"),
    (r"galer[ií]a|gal\.?", "Galería"),
    (r"edif[ií]cio|edificio|ed\.?", "Edificio"),
    (r"paseo", "Paseo"),
    (r"torre", "Torre"),
]

# Termos que encerram o nome do prédio dentro do endereço.
_FIM = r"(?=\s*(?:[,;\-–(]|\bloc(?:al)?\b|\bsala\b|\bpiso\b|\bandar\b|\bbox\b|\bn[º°o]?\.?\s*\d|\d|$))"

_RE_PREDIO = re.compile(
    r"\b(?P<prefixo>" + "|".join(p for p, _ in _PREFIXOS) + r")\s+(?P<nome>[A-Za-zÀ-ÿ'&. ]+?)" + _FIM,
    re.IGNORECASE,
)


def _canonico(prefixo: str) -> str:
    for padrao, forma in _PREFIXOS:
        if re.fullmatch(padrao, prefixo, re.IGNORECASE):
            return forma
    return prefixo.title()


def extrair_predio(endereco: object) -> str | None:
    """Devolve, por exemplo, "Shopping Paris" para "Av. X, Shopping Paris, Local 12"."""
    if not endereco:
        return None
    m = _RE_PREDIO.search(str(endereco))
    if not m:
        return None
    nome = re.sub(r"\s+", " ", m.group("nome")).strip(" .")
    if not nome or normalizar(nome) in {"del", "de", "la"}:
        return None
    nome = " ".join(p if p.isupper() and len(p) <= 3 else p.capitalize() for p in nome.split())
    return f"{_canonico(m.group('prefixo'))} {nome}"
