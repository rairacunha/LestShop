"""Limpeza antes de gravar no banco (autorizada em 23/11/2026).

* **Produtos:** ``slug`` único tirado do nome (sem acento, minúsculas, hífens). Dois
  produtos com o mesmo slug viram um só (as ofertas passam para o primeiro), para não
  aparecerem repetidos no menu do app.
* **Lojas:** ``nome_normalizado`` (chave sem acento, espaço nem sufixos como
  "Importados"), com a lista inicial de ``data/lojas_seed.csv`` (apelidos → nome
  canônico, shopping/galeria, endereço, zona e coordenadas; os dados de lugar só valem
  para a loja no mesmo lugar, não para uma filial em outro endereço). Duas lojas com a mesma chave
  e no mesmo lugar (até 150 m, ou sem coordenada) viram uma só; filiais em lugares
  diferentes continuam separadas. ``zona`` vem da lista inicial ou da distância à Ponte.
  Coordenada da lista inicial só preenche loja **sem** coordenada (a do site vale mais).
* **Ofertas:** sai a oferta "vitrine", "CPO", "reacondicionado" etc. e o acessório
  vendido na página de outro produto (``data/filtro_ofertas.json``). Ganham
  ``url_oferta`` (página do Compras Paraguai onde a oferta aparece) e ``coletado_em``.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
from .texto import normalizar

ARQ_SEED = config.DIR_DADOS / "lojas_seed.csv"
ARQ_FILTRO = ARQ_SEED.with_name("filtro_ofertas.json")
PONTE = (-25.5097, -54.6033)
DISTANCIA_MESMA_LOJA_M = 150.0
_SUFIXOS = ("importados", "importadora", "importacoes", "s a", "sa", "srl", "s r l", "ltda", "py", "cde")


def slug_produto(nome: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalizar(nome)).strip("-")


def chave_loja(nome: object) -> str:
    """'Shopping China Importados' -> 'shoppingchina'; 'Visão VIP' -> 'visaovip'."""
    txt = re.sub(r"[^a-z0-9 ]+", " ", normalizar(nome))
    txt = re.sub(r"\s+", " ", txt).strip()
    for suf in _SUFIXOS:
        txt = re.sub(rf"(?:^| ){suf}$", "", txt).strip()
    return txt.replace(" ", "")


def _metros(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def zona_por_distancia(lat: object, lon: object) -> str | None:
    if pd.isna(lat) or pd.isna(lon):
        return None
    d = _metros(PONTE, (float(lat), float(lon)))
    return "Microcentro" if d <= 1200 else "Perto do microcentro" if d <= 3000 else "Fora do centro"


@dataclass
class LojaSeed:
    chave: str
    nome: str
    loja_id: str | None
    shopping_galeria: str | None
    endereco: str | None
    zona: str | None
    latitude: float | None
    longitude: float | None
    origem_coordenada: str


def carregar_seed(caminho: Path = ARQ_SEED) -> tuple[dict[str, LojaSeed], dict[str, str]]:
    """(chave -> loja, apelido normalizado -> chave)."""
    lojas, apelidos = {}, {}
    if not Path(caminho).exists():
        return lojas, apelidos
    with open(caminho, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            v = {k: (x.strip() or None) for k, x in r.items()}
            s = LojaSeed(v["chave"], v["nome"], v["loja_id"], v["shopping_galeria"],
                         None if (v["endereco"] or "").lower() == "a confirmar" else v["endereco"],
                         v["zona"], float(v["latitude"]) if v["latitude"] else None,
                         float(v["longitude"]) if v["longitude"] else None, v["origem_coordenada"] or "")
            lojas[s.chave] = s
            for ap in [s.nome, *(v["apelidos"] or "").split("|")]:
                if ap and ap.strip():
                    apelidos[chave_loja(ap)] = s.chave
    return lojas, apelidos


def carregar_filtro(caminho: Path = ARQ_FILTRO) -> dict[str, list[str]]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8")) if Path(caminho).exists() else {}
    return {k: [normalizar(p) for p in dados.get(k, [])] for k in ("condicao", "acessorios")}


def motivo_descarte(titulo: object, nome_produto: object, filtro: dict[str, list[str]]) -> str | None:
    """Motivo para descartar a oferta, ou None se ela fica."""
    t = " " + re.sub(r"[^a-z0-9]+", " ", normalizar(titulo)).strip() + " "
    n = " " + re.sub(r"[^a-z0-9]+", " ", normalizar(nome_produto)).strip() + " "
    for p in filtro["condicao"]:
        if f" {p} " in t:
            return f"condição: {p}"
    for p in filtro["acessorios"]:
        if t.startswith(f" {p} ") and f" {p} " not in n:
            return f"acessório: {p}"
    return None


@dataclass
class Limpeza:
    lojas: pd.DataFrame
    produtos: pd.DataFrame
    ofertas: pd.DataFrame
    descartes: pd.DataFrame
    avisos: list[str] = field(default_factory=list)


def _unir_lojas(lojas: pd.DataFrame, seed: dict[str, LojaSeed], apelidos: dict[str, str]) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    lojas = lojas.copy()
    chaves = [chave_loja(n) for n in lojas["nome"]]
    lojas["nome_normalizado"] = [apelidos.get(c, c) for c in chaves]
    troca, avisos, manter = {}, [], []
    for chave, grupo in lojas.groupby("nome_normalizado", sort=False):
        restantes = list(grupo.index)
        while restantes:
            base = restantes.pop(0)
            manter.append(base)
            pb = (lojas.at[base, "latitude"], lojas.at[base, "longitude"])
            for outro in list(restantes):
                po = (lojas.at[outro, "latitude"], lojas.at[outro, "longitude"])
                sem_coord = pd.isna(pb[0]) or pd.isna(po[0])
                if sem_coord or _metros(pb, po) <= DISTANCIA_MESMA_LOJA_M:
                    restantes.remove(outro)
                    troca[lojas.at[outro, "loja_id"]] = lojas.at[base, "loja_id"]
                    avisos.append(f"Loja '{lojas.at[outro, 'nome']}' ({lojas.at[outro, 'loja_id']}) unida a "
                                  f"'{lojas.at[base, 'nome']}' ({lojas.at[base, 'loja_id']}): mesmo nome normalizado.")
                    for col in ("predio", "endereco", "latitude", "longitude", "abre", "fecha"):
                        if pd.isna(lojas.at[base, col]) and not pd.isna(lojas.at[outro, col]):
                            lojas.at[base, col] = lojas.at[outro, col]
    lojas = lojas.loc[manter].copy()
    for i in lojas.index:
        s = seed.get(lojas.at[i, "nome_normalizado"])
        if s is not None:
            lojas.at[i, "nome"] = s.nome
            la, lo = lojas.at[i, "latitude"], lojas.at[i, "longitude"]
            mesmo_lugar = (pd.isna(la) or pd.isna(lo) or s.latitude is None
                           or _metros((float(la), float(lo)), (s.latitude, s.longitude)) <= DISTANCIA_MESMA_LOJA_M)
            if not mesmo_lugar:  # filial em outro endereço: só o nome canônico
                lojas.at[i, "zona"] = zona_por_distancia(la, lo)
                continue
            if pd.isna(lojas.at[i, "predio"]) and s.shopping_galeria:
                lojas.at[i, "predio"] = s.shopping_galeria
            if pd.isna(lojas.at[i, "endereco"]) and s.endereco:
                lojas.at[i, "endereco"] = s.endereco
            if (pd.isna(lojas.at[i, "latitude"]) or pd.isna(lojas.at[i, "longitude"])) and s.latitude is not None:
                lojas.at[i, "latitude"], lojas.at[i, "longitude"] = s.latitude, s.longitude
                lojas.at[i, "coordenada_pendente"] = False
                avisos.append(f"Loja '{s.nome}' sem coordenada no site: usada a da lista inicial "
                              f"({s.origem_coordenada}).")
            lojas.at[i, "zona"] = s.zona or zona_por_distancia(lojas.at[i, "latitude"], lojas.at[i, "longitude"])
        else:
            lojas.at[i, "zona"] = zona_por_distancia(lojas.at[i, "latitude"], lojas.at[i, "longitude"])
    return lojas.reset_index(drop=True), troca, avisos


def preparar(lojas: pd.DataFrame, produtos: pd.DataFrame, ofertas: pd.DataFrame,
             seed_arq: Path = ARQ_SEED, filtro_arq: Path = ARQ_FILTRO) -> Limpeza:
    """Aplica a limpeza (ver o topo do módulo). Não muda preços nem datas."""
    from . import esquema

    lojas = esquema.padronizar(lojas, "lojas")
    produtos = esquema.padronizar(produtos, "produtos")
    ofertas = esquema.padronizar(ofertas, "ofertas")
    seed, apelidos = carregar_seed(seed_arq)
    filtro = carregar_filtro(filtro_arq)
    avisos: list[str] = []

    # Produtos: slug único.
    produtos = produtos.copy()
    produtos["slug"] = [s if isinstance(s, str) and s else slug_produto(n)
                        for s, n in zip(produtos["slug"], produtos["nome"])]
    troca_p = {}
    primeiro = {}
    for pid, slug in zip(produtos["produto_id"], produtos["slug"]):
        if slug in primeiro and primeiro[slug] != pid:
            troca_p[pid] = primeiro[slug]
        else:
            primeiro.setdefault(slug, pid)
    if troca_p:
        avisos += [f"Produto {a} unido a {b}: mesmo nome (slug)." for a, b in troca_p.items()]
        produtos = produtos[~produtos["produto_id"].isin(troca_p)].reset_index(drop=True)

    # Lojas: nome normalizado, lista inicial e zona.
    lojas, troca_l, av = _unir_lojas(lojas, seed, apelidos)
    avisos += av

    # Ofertas: novos campos, troca de ids e filtro de limpeza.
    ofertas = ofertas.copy()
    ofertas["produto_id"] = ofertas["produto_id"].map(lambda p: troca_p.get(p, p))
    ofertas["loja_id"] = ofertas["loja_id"].map(lambda l: troca_l.get(l, l))
    url = dict(zip(produtos["produto_id"], produtos["url_modelo"]))
    nome = dict(zip(produtos["produto_id"], produtos["nome"]))
    ofertas["url_oferta"] = [u if isinstance(u, str) and u else url.get(p)
                             for u, p in zip(ofertas["url_oferta"], ofertas["produto_id"])]
    ofertas["coletado_em"] = [c if isinstance(c, str) and c else d
                              for c, d in zip(ofertas["coletado_em"], ofertas["data_coleta"])]
    motivos = [motivo_descarte(t, nome.get(p), filtro) for t, p in zip(ofertas["titulo_oferta"], ofertas["produto_id"])]
    sai = pd.Series([m is not None for m in motivos], index=ofertas.index)
    descartes = pd.DataFrame({
        "data": ofertas.loc[sai, "data_coleta"], "termo": None,
        "url_modelo": ofertas.loc[sai, "url_oferta"], "loja_slug": ofertas.loc[sai, "loja_id"],
        "cidade": None, "motivo": [m for m in motivos if m is not None],
    }).reset_index(drop=True)
    ofertas = ofertas[~sai].reset_index(drop=True)
    return Limpeza(esquema.padronizar(lojas, "lojas"), esquema.padronizar(produtos, "produtos"),
                   esquema.padronizar(ofertas, "ofertas"), descartes, avisos)
