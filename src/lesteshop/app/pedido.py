"""Monta a instância a partir do que o turista digita.

Não repete nenhuma regra: valida a entrada e chama ``montar_instancia()`` da
Fase 2, que faz todo o pré-processamento aprovado (lojas sem coordenada, janelas,
padrões de horário, cota e alíquota da tabela, categorias fiscais).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from ..fiscal.categorias import MapaCategorias
from ..otimizacao.instancia import Instancia, hhmm_para_min, montar_instancia
from .base import BaseApp

PRIORIDADES = (1, 2, 3, 4, 5)


class ErroPedido(ValueError):
    """Entrada do turista inválida (mensagem pronta para a tela)."""


@dataclass
class ItemPedido:
    produto_id: str
    quantidade: int = 1
    prioridade: int = 3


def _hhmm(valor: str | dt.time) -> str:
    if isinstance(valor, dt.time):
        return f"{valor.hour:02d}:{valor.minute:02d}"
    return str(valor)


def validar_pedido(
    base: BaseApp,
    itens: list[ItemPedido],
    chegada: str | dt.time,
    saida: str | dt.time,
    orcamento: float | None,
) -> list[str]:
    """Lista de erros (vazia = pedido válido)."""
    erros = []
    if not itens:
        erros.append("Inclua pelo menos um item na lista de compras.")
    vistos = set()
    ids_base = set(base.produtos["produto_id"])
    for it in itens:
        nome = base.nome_produto(it.produto_id)
        if it.produto_id not in ids_base:
            erros.append(f"O produto {it.produto_id} não está na base de ofertas.")
        if it.produto_id in vistos:
            erros.append(f"{nome} aparece mais de uma vez na lista: ajuste a quantidade.")
        vistos.add(it.produto_id)
        if not isinstance(it.quantidade, int) or isinstance(it.quantidade, bool) or it.quantidade < 1:
            erros.append(f"A quantidade de {nome} deve ser um número inteiro a partir de 1.")
        if it.prioridade not in PRIORIDADES:
            erros.append(f"A prioridade de {nome} deve ser de 1 a 5.")
    try:
        if hhmm_para_min(_hhmm(saida)) <= hhmm_para_min(_hhmm(chegada)):
            erros.append("O horário de saída deve ser depois do horário de chegada.")
    except ValueError:
        erros.append("Horários devem estar no formato HH:MM.")
    if orcamento is not None and not orcamento > 0:
        erros.append("O orçamento deve ser maior que zero (ou deixe sem orçamento).")
    return erros


def montar_pedido(
    base: BaseApp,
    itens: list[ItemPedido],
    chegada: str | dt.time,
    saida: str | dt.time,
    orcamento: float | None = None,
    categorias: MapaCategorias | None = None,
) -> Instancia:
    """Instância do pedido. ``orcamento=None``: sem orçamento (B = cota).
    ``categorias``: padrão = ``data/categorias_fiscais.csv``."""
    erros = validar_pedido(base, itens, chegada, saida, orcamento)
    if erros:
        raise ErroPedido(" ".join(erros))
    meta = {
        "nome": "pedido", "tamanho": None, "n_lojas": base.n_lojas,
        "horario_chegada": _hhmm(chegada), "horario_saida": _hhmm(saida),
        "orcamento_usd": orcamento, "tipo_dado": base.origem,
    }
    lista = pd.DataFrame([
        {"produto_id": it.produto_id, "nome": base.nome_produto(it.produto_id),
         "quantidade": it.quantidade, "prioridade": it.prioridade}
        for it in itens
    ])
    return montar_instancia(
        nome="pedido", meta=meta, lojas_df=base.lojas,
        produtos_df=base.produtos.set_index("produto_id"), ofertas_df=base.ofertas,
        pontos=base.pontos, lista=lista, orcamento=orcamento, categorias=categorias,
    )
