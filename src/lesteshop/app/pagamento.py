"""Acréscimo por forma de pagamento (aprovado em 21/11/2026).

Nas lojas de Ciudad del Este o preço muda com a forma de pagamento. As taxas vêm de
``data/formas_pagamento.csv`` (observação de campo, valores estimados e editáveis, com a
origem registrada); não vêm do Compras Paraguai.

Regras:

* O acréscimo é igual em todas as lojas, então **o modelo e a escolha das lojas não
  mudam**: o roteiro é calculado com os preços do site (como antes) e só depois os
  valores são refeitos com a taxa (``com_acrescimo``).
* O acréscimo entra no valor dos produtos e o **imposto é calculado sobre o valor com a
  taxa**, porque é o valor da nota fiscal.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

from ..otimizacao.instancia import Instancia

ARQUIVO = Path(__file__).resolve().parents[3] / "data" / "formas_pagamento.csv"


@dataclass(frozen=True)
class FormaPagamento:
    forma_id: str
    nome: str
    acrescimo: float          # fração: 0.03 = 3%
    padrao: bool
    origem: str
    data_referencia: str

    @property
    def rotulo(self) -> str:
        pct = f"{self.acrescimo * 100:g}".replace(".", ",")
        return f"{self.nome} (+{pct}%)" if self.acrescimo else f"{self.nome} (sem acréscimo)"


def carregar_formas(caminho: Path = ARQUIVO) -> list[FormaPagamento]:
    """Lê as formas de pagamento. Exige uma com acréscimo 0 (dinheiro, a referência) e
    exatamente uma marcada como padrão."""
    with open(caminho, encoding="utf-8", newline="") as f:
        formas = [FormaPagamento(
            forma_id=r["forma_id"].strip(), nome=r["nome"].strip(), acrescimo=float(r["acrescimo"]),
            padrao=r["padrao"].strip().lower() == "sim", origem=r["origem"].strip(),
            data_referencia=r["data_referencia"].strip(),
        ) for r in csv.DictReader(f)]
    if not formas:
        raise ValueError(f"{caminho.name}: nenhuma forma de pagamento.")
    if any(not 0 <= fp.acrescimo < 1 for fp in formas):
        raise ValueError(f"{caminho.name}: acréscimo deve estar entre 0 e 1 (ex.: 0.03 = 3%).")
    if not any(fp.acrescimo == 0 for fp in formas):
        raise ValueError(f"{caminho.name}: falta uma forma sem acréscimo (dinheiro), usada como referência.")
    if sum(fp.padrao for fp in formas) != 1:
        raise ValueError(f"{caminho.name}: marque exatamente uma forma como padrão.")
    if len({fp.forma_id for fp in formas}) != len(formas):
        raise ValueError(f"{caminho.name}: forma_id repetido.")
    return formas


def com_acrescimo(inst: Instancia, acrescimo: float) -> Instancia:
    """Cópia da instância com os preços já com o acréscimo (valor da nota fiscal).

    Usada só para refazer os valores do roteiro já escolhido (``descrever``): gasto,
    imposto sobre o valor com a taxa, situação da cota e alertas fiscais. O orçamento
    (B, que no app nunca limita) sobe na mesma proporção."""
    if acrescimo == 0:
        return inst
    fator = 1 + acrescimo
    return replace(inst, preco={c: p * fator for c, p in inst.preco.items()},
                   orcamento=inst.orcamento * fator)
