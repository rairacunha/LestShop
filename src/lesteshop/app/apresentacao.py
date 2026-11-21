"""Transforma o resultado de ``descrever()`` em tabelas e textos para a tela.

Sem Streamlit, para poder ser testado. Todos os cálculos continuam em US$; o R$
é só para exibição (``usd_para_brl``).
"""

from __future__ import annotations

import pandas as pd

from ..data.cotacao import Cotacao, usd_para_brl
from ..otimizacao.instancia import Instancia, min_para_hhmm
from ..otimizacao.rota import agenda
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


def tabela_fora(d: dict, inst: Instancia, orcamento_limita: bool = True) -> pd.DataFrame:
    """Itens deixados de fora, com o motivo. ``orcamento_limita=False``: o orçamento
    não limitou a compra (app), então o motivo só pode ser o horário."""
    idx = {it.produto_id: k for k, it in enumerate(inst.itens)}
    linhas = []
    for it in d["nao_comprados"]:
        k = idx.get(it["produto_id"])
        if k is None or not inst.lojas_do_item(k):
            motivo = "nenhuma loja disponível vende este item"
        else:
            motivo = ("não coube no orçamento ou no horário, ou não compensou o custo" if orcamento_limita
                      else "não deu tempo de passar na loja dentro do horário da viagem e das lojas")
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
        "situacao_cota": situacao_cota(d),
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


def aviso_orcamento(d: dict, orcamento: float | None, cotacao: Cotacao | None) -> str | None:
    """Aviso quando o custo total (produtos + imposto) passa do orçamento de referência."""
    if orcamento is None:
        return None
    custo = d["resumo"]["custo_total"]
    if custo <= orcamento + 1e-6:
        return None
    excesso = custo - orcamento
    brl = em_brl(excesso, cotacao)
    extra = f" ({fmt_brl(brl)})" if brl is not None else ""
    return (f"O custo total ({fmt_usd(custo)}) passa do seu orçamento de {fmt_usd(orcamento)} "
            f"em {fmt_usd(excesso)}{extra}. Todos os itens foram mantidos.")



def situacao_cota(d: dict) -> str:
    """Situação da cota com valores no formato brasileiro."""
    r = d["resumo"]
    if r["excedente"] <= 0:
        return "dentro da cota"
    return f"excede a cota em {fmt_usd(r['excedente'])} (imposto {fmt_usd(r['imposto'])})"


def _imposto(gasto: float, inst: Instancia) -> float:
    return inst.aliquota * max(0.0, gasto - inst.cota)


def comparativo_primeira_loja(d: dict, inst: Instancia) -> dict | None:
    """Simula comprar tudo na 1ª loja do roteiro e compara com o roteiro sugerido
    (decidido em 21/11/2026).

    Itens que a 1ª loja não vende ficam de fora da comparação (e são listados). Os dois
    cenários são comparados só nos itens que a 1ª loja vende; o imposto de cada cenário
    é recalculado sobre o gasto desses itens (cota integral). ``None`` se o roteiro tem
    menos de duas lojas (não há o que comparar)."""
    if len(d["roteiro"]) < 2:
        return None
    no = {l.loja_id: i for i, l in enumerate(inst.lojas, start=1)}
    idx = {it.produto_id: k for k, it in enumerate(inst.itens)}
    primeira = d["roteiro"][0]
    i1 = no[primeira["loja_id"]]
    linhas, faltam = [], []
    g_rota = g_uma = 0.0
    for p in d["roteiro"]:
        for c in p["compras"]:
            k = idx[c["produto_id"]]
            q = inst.itens[k].quantidade
            preco_rota = inst.preco[(no[p["loja_id"]], k)]
            preco_uma = inst.preco.get((i1, k))
            if preco_uma is None:
                faltam.append(c["nome"])
                linhas.append({"Item": c["nome"], "Qtd.": q, "Loja no roteiro": p["nome"],
                               "No roteiro (US$)": fmt_usd(preco_rota * q),
                               f"Só na {primeira['nome']} (US$)": "não vende", "Diferença (US$)": "—"})
                continue
            g_rota += preco_rota * q
            g_uma += preco_uma * q
            linhas.append({"Item": c["nome"], "Qtd.": q, "Loja no roteiro": p["nome"],
                           "No roteiro (US$)": fmt_usd(preco_rota * q),
                           f"Só na {primeira['nome']} (US$)": fmt_usd(preco_uma * q),
                           "Diferença (US$)": fmt_usd((preco_uma - preco_rota) * q)})
    ag = agenda([i1], inst)
    custo_rota = g_rota + _imposto(g_rota, inst)
    custo_uma = g_uma + _imposto(g_uma, inst)
    return {
        "loja": primeira["nome"],
        "tabela": pd.DataFrame(linhas),
        "faltam": faltam,
        "gasto_rota": g_rota, "gasto_uma": g_uma,
        "custo_rota": custo_rota, "custo_uma": custo_uma,
        "economia": custo_uma - custo_rota,
        "retorno_rota": d["horario_retorno"], "retorno_uma": min_para_hhmm(ag.retorno),
        "lojas_rota": len(d["roteiro"]),
    }
