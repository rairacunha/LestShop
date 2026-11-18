"""Transforma o resultado de ``descrever()`` em tabelas e textos para a tela.

Sem Streamlit, para poder ser testado. Todos os cálculos continuam em US$; o R$
é só para exibição (``usd_para_brl``).
"""

from __future__ import annotations

import pandas as pd

from ..data.cotacao import Cotacao, usd_para_brl
from ..otimizacao.instancia import Instancia
from .base import BaseApp

SITUACAO_LIMITE = {"abaixo": "dentro do limite", "no_limite": "no limite", "acima": "ACIMA do limite"}


def _milhar(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_usd(valor: float) -> str:
    return f"US$ {_milhar(valor)}"


def fmt_brl(valor: float | None) -> str:
    return "—" if valor is None else f"R$ {_milhar(valor)}"


def em_brl(valor_usd: float, cotacao: Cotacao | None) -> float | None:
    return None if cotacao is None else usd_para_brl(valor_usd, cotacao)


def fmt_data(iso: str | None) -> str:
    if not iso:
        return "—"
    a, m, d = str(iso)[:10].split("-")
    return f"{d}/{m}/{a}"


def texto_origem(base: BaseApp) -> tuple[str, str]:
    """(nível, texto) para o aviso de origem dos dados. Nível: ``ok`` ou ``atencao``."""
    ini, fim = base.data_coleta
    datas = fmt_data(fim) if ini == fim else f"{fmt_data(ini)} a {fmt_data(fim)}"
    if base.origem == "real":
        return "ok", f"Preços do Compras Paraguai, coletados em {datas}. Os preços do site mudam com o tempo."
    if base.origem == "mista":
        return "atencao", (f"Base MISTA: parte dos preços é FICTÍCIA (inventada para teste). "
                           f"Datas das ofertas: {datas}.")
    return "atencao", ("Base FICTÍCIA: lojas e preços inventados para teste do app. "
                       "Não use estes valores para planejar compras.")


def totais(d: dict, cotacao: Cotacao | None) -> list[tuple[str, str, str]]:
    """(rótulo, US$, R$) de gasto, imposto e custo total."""
    r = d["resumo"]
    linhas = [("Gasto com produtos", r["gasto_produtos"]), ("Imposto estimado", r["imposto"]),
              ("Custo total", r["custo_total"])]
    return [(rot, fmt_usd(v), fmt_brl(em_brl(v, cotacao))) for rot, v in linhas]


def tabela_itens(d: dict, base: BaseApp, cotacao: Cotacao | None) -> pd.DataFrame:
    linhas = []
    for parada in d["roteiro"]:
        for c in parada["compras"]:
            sub = c["preco_usd"] * c["quantidade"]
            info = base.info_oferta(parada["loja_id"], c["produto_id"])
            linhas.append({
                "Item": c["nome"], "Qtd.": c["quantidade"], "Loja": parada["nome"],
                "Preço unit. (US$)": fmt_usd(c["preco_usd"]), "Subtotal (US$)": fmt_usd(sub),
                "Subtotal (R$)": fmt_brl(em_brl(sub, cotacao)),
                "Coletado em": fmt_data(info["data_coleta"]),
                "Origem": "real" if info["tipo_dado"] == "real" else "fictícia",
            })
    return pd.DataFrame(linhas)


def tabela_roteiro(d: dict) -> pd.DataFrame:
    linhas = [{"Ordem": "—", "Local": "Ponte da Amizade (lado paraguaio)", "Prédio": "",
               "Chegada": d["horario_chegada"], "Atendimento": "", "Saída": d["horario_chegada"],
               "Comprar": "início do passeio"}]
    for p in d["roteiro"]:
        linhas.append({
            "Ordem": str(p["ordem"]), "Local": p["nome"], "Prédio": p["predio"] or "",
            "Chegada": p["chegada"], "Atendimento": p["inicio_atendimento"], "Saída": p["saida"],
            "Comprar": ", ".join(f"{c['quantidade']}× {c['nome']}" for c in p["compras"]),
        })
    linhas.append({"Ordem": "—", "Local": "Volta à Ponte da Amizade", "Prédio": "",
                   "Chegada": d["horario_retorno"], "Atendimento": "", "Saída": "", "Comprar": ""})
    return pd.DataFrame(linhas)


def tabela_fora(d: dict, inst: Instancia) -> pd.DataFrame:
    """Itens deixados de fora, com o motivo."""
    idx = {it.produto_id: k for k, it in enumerate(inst.itens)}
    linhas = []
    for it in d["nao_comprados"]:
        k = idx.get(it["produto_id"])
        if k is None or not inst.lojas_do_item(k):
            motivo = "nenhuma loja disponível vende este item"
        else:
            motivo = "não coube no orçamento ou no horário, ou não compensou o custo"
        linhas.append({"Item": it["nome"], "Prioridade": it["prioridade"], "Motivo": motivo})
    return pd.DataFrame(linhas)


def tabela_limites(fiscal: dict) -> pd.DataFrame:
    def num(v: float) -> str:
        return f"{v:g}".replace(".", ",")

    return pd.DataFrame([
        {"Limite": s["descricao"] + (f" ({s['produto']})" if s["contagem"] == "identicos" and s["produto"] else ""),
         "Usado": f"{num(s['usado'])} {s['unidade']}", "Limite máximo": f"{num(s['limite'])} {s['unidade']}",
         "Situação": SITUACAO_LIMITE.get(s["situacao"], s["situacao"])}
        for s in fiscal["limites"]
    ])


def resumo_fiscal(d: dict, cotacao: Cotacao | None) -> dict:
    """Textos do bloco fiscal."""
    f = d["fiscal"]
    sem_cota = f["imposto_sem_cota_usd"]
    return {
        "situacao_cota": d["situacao_cota"],
        "cota": f"{fmt_usd(f['cota_usd'])} por pessoa, via {f['via']} ({f['fonte_cota']})",
        "declaracao": ("Sim: preencher a e-DBV e passar pelo canal \"bens a declarar\"."
                       if f["declaracao_necessaria"] else "Não é necessária."),
        "imposto_sem_cota": (None if sem_cota is None else
                             f"{fmt_usd(sem_cota)} ({fmt_brl(em_brl(sem_cota, cotacao))}), se a bagagem "
                             "perder a cota por passar de um limite de unidades"),
        "alertas": f["alertas"],
        "avisos": f["avisos"],
        "premissa": f["premissa"],
        "data_referencia": fmt_data(f["data_referencia"]),
    }


def texto_solver(d: dict) -> str | None:
    """Aviso quando o modelo exato parou no tempo limite sem provar o ótimo."""
    info = d.get("info", {})
    if info.get("status") not in (None, "otimo"):
        gap = info.get("gap")
        extra = f" (distância máxima do ótimo: {gap:.1%})" if isinstance(gap, (int, float)) else ""
        return f"Melhor roteiro encontrado dentro do tempo limite{extra}."
    return None
