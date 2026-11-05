"""Leitura e pré-processamento de uma instância para o modelo da Fase 2.

Uma instância é uma pasta com lojas.csv, produtos.csv, ofertas.csv,
pontos_partida.csv, lista_compras.csv e metadata.json (formato da Fase 1).

Pré-processamento (decisões aprovadas):

* lojas com ``coordenada_pendente = true`` ficam de fora, com aviso listando os
  itens da lista que perderam essa opção de compra;
* só entram as lojas que vendem pelo menos um item da lista;
* oferta repetida da mesma loja para o mesmo produto: vale a de menor preço;
* ``abre``/``fecha``/``tempo_permanencia_min`` vazios recebem os padrões de ``config``;
* a janela de cada loja é recortada pela janela do turista [H⁰, H¹]; loja cuja
  janela recortada não comporta a permanência fica de fora, com aviso.

Tempos em minutos desde 00:00; dinheiro em US$.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .distancias import matriz_tempos
from ..data.sources.fonte_csv import FonteCSV

_DO_METADATA = "instancia"  # sentinela: usar o orçamento do metadata.json


def hhmm_para_min(valor: object, padrao: str | None = None) -> float:
    """'07:30' -> 450.0. Vazio usa ``padrao``."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)) or str(valor).strip() == "":
        if padrao is None:
            raise ValueError("Horário vazio sem valor padrão.")
        valor = padrao
    h, m = str(valor).strip().split(":")
    return int(h) * 60 + int(m)


def min_para_hhmm(minutos: float) -> str:
    total = int(round(minutos))
    return f"{total // 60:02d}:{total % 60:02d}"


@dataclass
class Item:
    produto_id: str
    nome: str
    quantidade: int
    prioridade: int
    peso_kg: float | None
    volume_l: float | None


@dataclass
class Loja:
    loja_id: str
    nome: str
    predio: str | None
    latitude: float
    longitude: float
    abre: float          # janela recortada pela janela do turista (min)
    fecha: float
    permanencia: float


@dataclass
class Instancia:
    """Dados prontos para o modelo. Nó 0 = Ponte; nós 1..m = ``lojas``."""

    nome: str
    tamanho: str | None
    itens: list[Item]
    lojas: list[Loja]
    # preco[(i, k)] = preço unitário em US$ do item k (índice em ``itens``) na loja
    # i (nó 1..m). Só existe a chave se a loja vende o item.
    preco: dict[tuple[int, int], float]
    t: np.ndarray                     # (m+1) × (m+1), minutos
    cota: float
    aliquota: float
    orcamento: float                  # B (= cota quando não informado)
    orcamento_informado: bool
    chegada: float                    # H⁰ (min)
    saida: float                      # H¹ (min)
    n_lojas_instancia: int            # número real de lojas da instância (metadata)
    peso_max_kg: float | None = None  # bagagem (desligada por padrão)
    volume_max_l: float | None = None
    avisos: list[str] = field(default_factory=list)
    lojas_excluidas: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # --- atalhos -------------------------------------------------------------
    @property
    def m(self) -> int:
        return len(self.lojas)

    @property
    def nos_lojas(self) -> range:
        return range(1, self.m + 1)

    @property
    def t_max(self) -> float:
        """T_max = H¹ − H⁰ (min)."""
        return self.saida - self.chegada

    def loja(self, i: int) -> Loja:
        return self.lojas[i - 1]

    def lojas_do_item(self, k: int) -> list[int]:
        return [i for i in self.nos_lojas if (i, k) in self.preco]

    def itens_da_loja(self, i: int) -> list[int]:
        return [k for k in range(len(self.itens)) if (i, k) in self.preco]

    def custo_item(self, i: int, k: int) -> float:
        """p_ik · q_k."""
        return self.preco[(i, k)] * self.itens[k].quantidade

    def lambda_(self, r: float) -> float:
        """λ = 1 / (B + r·T_max + 1)."""
        return 1.0 / (self.orcamento + r * self.t_max + 1.0)

    def big_m(self) -> float:
        """M = max(fecha) + max(s_i) + max(t_ij) − min(abre), com as janelas recortadas."""
        if not self.lojas:
            return 0.0
        return (
            max(l.fecha for l in self.lojas)
            + max(l.permanencia for l in self.lojas)
            + float(self.t.max())
            - min(l.abre for l in self.lojas)
        )


def carregar_instancia(
    pasta: str | Path,
    orcamento: float | None | str = _DO_METADATA,
    peso_max_kg: float | None = None,
    volume_max_l: float | None = None,
) -> Instancia:
    """Lê e pré-processa uma instância.

    ``orcamento``: ``"instancia"`` (padrão) usa ``orcamento_usd`` do metadata.json;
    ``None`` = turista não informou orçamento (teto = cota); um número substitui.
    """
    pasta = Path(pasta)
    meta = json.loads((pasta / "metadata.json").read_text(encoding="utf-8"))
    fonte = FonteCSV(pasta)
    lojas_df = fonte.carregar_lojas()
    produtos_df = fonte.carregar_produtos().set_index("produto_id")
    ofertas_df = fonte.carregar_ofertas()
    pontos = fonte.carregar_pontos_partida()
    lista = pd.read_csv(pasta / "lista_compras.csv", dtype={"produto_id": str})
    return montar_instancia(
        nome=meta.get("nome", pasta.name), meta=meta, lojas_df=lojas_df,
        produtos_df=produtos_df, ofertas_df=ofertas_df, pontos=pontos, lista=lista,
        orcamento=orcamento, peso_max_kg=peso_max_kg, volume_max_l=volume_max_l,
    )


def _float_ou_none(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def montar_instancia(
    nome: str,
    meta: dict,
    lojas_df: pd.DataFrame,
    produtos_df: pd.DataFrame,
    ofertas_df: pd.DataFrame,
    pontos: pd.DataFrame,
    lista: pd.DataFrame,
    orcamento: float | None | str = _DO_METADATA,
    peso_max_kg: float | None = None,
    volume_max_l: float | None = None,
) -> Instancia:
    avisos: list[str] = []
    excluidas: list[dict] = []
    cota = float(meta.get("cota_disponivel_usd", 500.0))
    aliquota = float(meta.get("aliquota_excedente", 0.5))
    if orcamento == _DO_METADATA:
        orcamento = _float_ou_none(meta.get("orcamento_usd"))
    orcamento_informado = orcamento is not None
    B = float(orcamento) if orcamento_informado else cota
    H0 = hhmm_para_min(meta.get("horario_chegada"), "08:00")
    H1 = hhmm_para_min(meta.get("horario_saida"), "16:00")
    if H1 <= H0:
        raise ValueError(f"{nome}: horario_saida deve ser maior que horario_chegada.")

    # Itens da lista
    itens: list[Item] = []
    for _, row in lista.iterrows():
        pid = str(row["produto_id"])
        prod = produtos_df.loc[pid] if pid in produtos_df.index else None
        itens.append(Item(
            produto_id=pid,
            nome=str(row.get("nome") or (prod["nome"] if prod is not None else pid)),
            quantidade=int(row.get("quantidade", 1) or 1),
            prioridade=int(row["prioridade"]),
            peso_kg=_float_ou_none(prod["peso_kg"]) if prod is not None else None,
            volume_l=_float_ou_none(prod["volume_l"]) if prod is not None else None,
        ))
    idx_item = {it.produto_id: k for k, it in enumerate(itens)}

    # Ofertas dos itens da lista, menor preço por (loja, produto)
    of = ofertas_df[ofertas_df["produto_id"].isin(idx_item)]
    of = of[of["preco_usd"] > 0]
    menor = of.groupby(["loja_id", "produto_id"])["preco_usd"].min()
    if len(menor) < len(of):
        avisos.append(f"{len(of) - len(menor)} oferta(s) repetida(s) na mesma loja: usado o menor preço.")

    lojas_df = lojas_df.set_index("loja_id")
    vende: dict[str, list[str]] = {}
    for (lid, pid) in menor.index:
        vende.setdefault(lid, []).append(pid)

    candidatas: list[Loja] = []
    for lid in sorted(vende):
        if lid not in lojas_df.index:
            avisos.append(f"Oferta da loja {lid} ignorada: loja não está em lojas.csv.")
            continue
        l = lojas_df.loc[lid]
        nomes_itens = [itens[idx_item[p]].nome for p in sorted(vende[lid])]
        lat, lon = _float_ou_none(l["latitude"]), _float_ou_none(l["longitude"])
        if bool(l["coordenada_pendente"]) or lat is None or lon is None:
            excluidas.append({"loja_id": lid, "motivo": "coordenada pendente", "itens": nomes_itens})
            avisos.append(
                f"Loja {lid} ({l['nome']}) excluída por coordenada pendente; itens da lista "
                f"que perderam essa opção de compra: {', '.join(nomes_itens)}."
            )
            continue
        abre = max(hhmm_para_min(l["abre"], config.ABRE_PADRAO), H0)
        fecha = min(hhmm_para_min(l["fecha"], config.FECHA_PADRAO), H1)
        perm = _float_ou_none(l["tempo_permanencia_min"])
        perm = config.PERMANENCIA_PADRAO_MIN if perm is None else perm
        if abre + perm > fecha:
            excluidas.append({"loja_id": lid, "motivo": "fora da janela de tempo", "itens": nomes_itens})
            avisos.append(
                f"Loja {lid} ({l['nome']}) excluída: o horário dela não cabe na janela do turista; "
                f"itens que perderam essa opção: {', '.join(nomes_itens)}."
            )
            continue
        candidatas.append(Loja(lid, str(l["nome"]), l["predio"], lat, lon, abre, fecha, perm))

    preco: dict[tuple[int, int], float] = {}
    for i, loja in enumerate(candidatas, start=1):
        for pid in vende[loja.loja_id]:
            preco[(i, idx_item[pid])] = float(menor[(loja.loja_id, pid)])

    for k, it in enumerate(itens):
        if not any((i, k) in preco for i in range(1, len(candidatas) + 1)):
            avisos.append(f"Item {it.produto_id} ({it.nome}) não tem oferta disponível: não será comprado.")

    p0 = pontos[pontos["id"].astype(int) == 0]
    if p0.empty:
        raise ValueError(f"{nome}: pontos_partida.csv sem o nó 0 (Ponte da Amizade).")
    coords = [(float(p0.iloc[0]["latitude"]), float(p0.iloc[0]["longitude"]))]
    coords += [(l.latitude, l.longitude) for l in candidatas]
    t = matriz_tempos(coords, [None] + [l.predio for l in candidatas])

    return Instancia(
        nome=nome, tamanho=meta.get("tamanho"), itens=itens, lojas=candidatas, preco=preco,
        t=t, cota=cota, aliquota=aliquota, orcamento=B, orcamento_informado=orcamento_informado,
        chegada=H0, saida=H1, n_lojas_instancia=int(meta.get("n_lojas", len(lojas_df))),
        peso_max_kg=peso_max_kg, volume_max_l=volume_max_l, avisos=avisos,
        lojas_excluidas=excluidas, metadata=meta,
    )
