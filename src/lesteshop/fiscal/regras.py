"""Tabela de regras fiscais da bagagem (``data/regras_fiscais.csv``).

A tabela é versionada: cada linha tem ``vigencia_inicio``, e para cada
``regra_id`` vale a linha mais recente que já está em vigor na data de
referência. Assim uma mudança na lei entra como linha nova, sem apagar a antiga.

Colunas:

* ``regra_id``: identificador da regra (``cota_terrestre``, ``bebidas``...);
* ``tipo_limite``: ``valor`` (US$), ``quantidade`` (unidades, maços, gramas) ou ``litros``;
* ``categoria_fiscal``: categoria a que a regra se aplica (``todas`` para a cota);
* ``contagem``: ``total`` (soma da categoria) ou ``identicos`` (por produto);
* ``limite``, ``unidade``, ``via``;
* ``valor_unitario_min_usd`` / ``valor_unitario_max_usd``: faixa de preço unitário
  coberta pela regra (mínimo inclusivo, máximo exclusivo; vazio = sem limite);
* ``consequencia``: ``rte_excedente`` (50% sobre o que passar da cota),
  ``regime_comum`` (o excesso não pode ser regularizado como bagagem) ou
  ``perde_cota`` (a bagagem vai para o RTE sem a isenção);
* ``descricao``, ``fonte`` (norma e dispositivo), ``vigencia_inicio`` (AAAA-MM-DD).

Fontes e textos das normas: ``docs/legislacao_bagagem.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from ..data import config as config_dados

CAMINHO_REGRAS = config_dados.DIR_DADOS / "regras_fiscais.csv"
VIA_PADRAO = "terrestre"
REGRA_COTA = "cota_terrestre"

TIPOS_LIMITE = ("valor", "quantidade", "litros")
CONTAGENS = ("total", "identicos")
CONSEQUENCIAS = ("rte_excedente", "regime_comum", "perde_cota")
COLUNAS = [
    "regra_id", "tipo_limite", "categoria_fiscal", "contagem", "limite", "unidade", "via",
    "valor_unitario_min_usd", "valor_unitario_max_usd", "consequencia", "descricao", "fonte",
    "vigencia_inicio",
]


class ErroRegras(ValueError):
    """Tabela de regras fiscais inválida."""


@dataclass(frozen=True)
class Regra:
    regra_id: str
    tipo_limite: str
    categoria_fiscal: str
    contagem: str
    limite: float
    unidade: str
    via: str
    valor_unitario_min: float | None
    valor_unitario_max: float | None
    consequencia: str
    descricao: str
    fonte: str
    vigencia_inicio: date

    def cobre_valor(self, preco_unitario: float) -> bool:
        """O preço unitário está na faixa da regra (mínimo inclusivo, máximo exclusivo)?"""
        if self.valor_unitario_min is not None and preco_unitario < self.valor_unitario_min:
            return False
        if self.valor_unitario_max is not None and preco_unitario >= self.valor_unitario_max:
            return False
        return True


@dataclass(frozen=True)
class RegrasFiscais:
    """Regras em vigor numa data, para uma via de transporte."""

    data_referencia: date
    via: str
    cota: Regra
    limites: tuple[Regra, ...]

    @property
    def cota_usd(self) -> float:
        return self.cota.limite


def _opcional(v) -> float | None:
    if v is None or (isinstance(v, float) and math.isnan(v)) or str(v).strip() == "":
        return None
    return float(v)


def _data(v) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v).strip())


def ler_tabela(caminho: str | Path = CAMINHO_REGRAS) -> list[Regra]:
    """Lê e valida todas as linhas da tabela (todas as vigências)."""
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    faltando = [c for c in COLUNAS if c not in df.columns]
    if faltando:
        raise ErroRegras(f"{caminho}: faltam as colunas {', '.join(faltando)}.")
    regras = []
    for n, row in enumerate(df.to_dict("records"), start=2):
        try:
            r = Regra(
                regra_id=row["regra_id"].strip(), tipo_limite=row["tipo_limite"].strip(),
                categoria_fiscal=row["categoria_fiscal"].strip(), contagem=row["contagem"].strip(),
                limite=float(row["limite"]), unidade=row["unidade"].strip(), via=row["via"].strip(),
                valor_unitario_min=_opcional(row["valor_unitario_min_usd"]),
                valor_unitario_max=_opcional(row["valor_unitario_max_usd"]),
                consequencia=row["consequencia"].strip(), descricao=row["descricao"].strip(),
                fonte=row["fonte"].strip(), vigencia_inicio=_data(row["vigencia_inicio"]),
            )
        except (KeyError, ValueError) as e:
            raise ErroRegras(f"{caminho}, linha {n}: {e}") from e
        if not r.regra_id:
            raise ErroRegras(f"{caminho}, linha {n}: regra_id vazio.")
        if r.tipo_limite not in TIPOS_LIMITE:
            raise ErroRegras(f"{caminho}, linha {n}: tipo_limite '{r.tipo_limite}' inválido.")
        if r.contagem not in CONTAGENS:
            raise ErroRegras(f"{caminho}, linha {n}: contagem '{r.contagem}' inválida.")
        if r.consequencia not in CONSEQUENCIAS:
            raise ErroRegras(f"{caminho}, linha {n}: consequencia '{r.consequencia}' inválida.")
        if r.limite < 0:
            raise ErroRegras(f"{caminho}, linha {n}: limite negativo.")
        regras.append(r)
    return regras


def carregar_regras(
    caminho: str | Path = CAMINHO_REGRAS,
    data: date | str | None = None,
    via: str = VIA_PADRAO,
) -> RegrasFiscais:
    """Regras em vigor em ``data`` (padrão: hoje) para a ``via`` de transporte."""
    ref = _data(data) if data is not None else date.today()
    vigentes: dict[str, Regra] = {}
    for r in ler_tabela(caminho):
        if r.via != via or r.vigencia_inicio > ref:
            continue
        atual = vigentes.get(r.regra_id)
        if atual is None or r.vigencia_inicio > atual.vigencia_inicio:
            vigentes[r.regra_id] = r
        elif r.vigencia_inicio == atual.vigencia_inicio:
            raise ErroRegras(f"{caminho}: duas linhas de '{r.regra_id}' com a mesma vigência.")
    cota = vigentes.pop(REGRA_COTA, None)
    if cota is None:
        raise ErroRegras(f"{caminho}: nenhuma regra '{REGRA_COTA}' em vigor em {ref} (via {via}).")
    if cota.tipo_limite != "valor":
        raise ErroRegras(f"{caminho}: a regra '{REGRA_COTA}' deve ser do tipo 'valor'.")
    return RegrasFiscais(ref, via, cota, tuple(vigentes[k] for k in sorted(vigentes)))
