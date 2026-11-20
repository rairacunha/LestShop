"""Catálogo curado do app (``data/catalogo_app.json``).

Lista fixa de produtos populares que aparece no menu suspenso. Cada item tem:

* ``id``: identificador estável do item no catálogo;
* ``nome``: nome mostrado ao turista;
* ``termo``: termo de busca "limpo" usado no site quando não há ``url_modelo``;
* ``categoria``: categoria do projeto (a mesma de ``data/categorias_fiscais.csv``);
* ``url_modelo`` (opcional): página do modelo no Compras Paraguai; quando existe, a
  consulta vai direto a ela (uma requisição a menos e sem risco de a busca achar outro
  produto);
* ``conteudo_por_unidade`` (opcional): litros por garrafa, para o limite de bebidas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..data.sources.parser_cp import RE_URL_MODELO, _caminho
from . import config


@dataclass(frozen=True)
class ItemCatalogo:
    id: str
    nome: str
    termo: str
    categoria: str
    url_modelo: str | None = None
    conteudo_por_unidade: float | None = None

    @property
    def rotulo(self) -> str:
        return f"{self.nome} ({self.categoria})"


def carregar_catalogo_app(caminho: str | Path = config.CAMINHO_CATALOGO_APP) -> list[ItemCatalogo]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    itens, vistos, erros = [], set(), []
    for i, d in enumerate(dados.get("produtos", [])):
        faltando = [c for c in ("id", "nome", "termo", "categoria") if not str(d.get(c) or "").strip()]
        if faltando:
            erros.append(f"item {i}: faltam {', '.join(faltando)}")
            continue
        if d["id"] in vistos:
            erros.append(f"id repetido: {d['id']}")
        vistos.add(d["id"])
        url = d.get("url_modelo") or None
        if url and not RE_URL_MODELO.match(_caminho(url)):
            erros.append(f"{d['id']}: url_modelo não é uma página de modelo ({url})")
        conteudo = d.get("conteudo_por_unidade")
        itens.append(ItemCatalogo(d["id"], d["nome"].strip(), d["termo"].strip(), d["categoria"].strip(),
                                  url, float(conteudo) if conteudo is not None else None))
    if erros:
        raise ValueError(f"{caminho}: " + "; ".join(erros))
    return itens
