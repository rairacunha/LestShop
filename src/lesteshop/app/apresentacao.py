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
    linhas = [("Produtos", r["gasto_produtos"]), ("Imposto da Receita", r["imposto"]),
              ("Total a pagar", r["custo_total"])]
    return [(rot, fmt_usd(v), fmt_brl(em_brl(v, cotacao))) for rot, v in linhas]


def tabela_itens(d: dict, base: BaseApp, cotacao: Cotacao | None) -> pd.DataFrame:
    linhas = []
    for parada in d["roteiro"]:
        for c in parada["compras"]:
            sub = c["preco_usd"] * c["quantidade"]
            info = base.info_oferta(parada["loja_id"], c["produto_id"])
            linhas.append({
                "Parada": parada["ordem"], "Produto": c["nome"], "Qtd.": c["quantidade"],
                "Loja": parada["nome"], "Preço (US$)": fmt_usd(c["preco_usd"]),
                "Total (US$)": fmt_usd(sub), "Total (R$)": fmt_brl(em_brl(sub, cotacao)),
                "Preço visto em": fmt_data(info["data_coleta"]),
                "Preço": "real" if info["tipo_dado"] == "real" else "fictício (teste)",
            })
    return pd.DataFrame(linhas)


def tabela_roteiro(d: dict) -> pd.DataFrame:
    linhas = [{"Parada": "Início", "Onde": "Ponte da Amizade (lado paraguaio)", "Prédio": "",
               "Chega às": d["horario_chegada"], "Atendido às": "", "Sai às": d["horario_chegada"],
               "O que comprar": "começo do passeio"}]
    for p in d["roteiro"]:
        linhas.append({
            "Parada": str(p["ordem"]), "Onde": p["nome"], "Prédio": p["predio"] or "",
            "Chega às": p["chegada"], "Atendido às": p["inicio_atendimento"], "Sai às": p["saida"],
            "O que comprar": ", ".join(f"{c['quantidade']}× {c['nome']}" for c in p["compras"]),
        })
    linhas.append({"Parada": "Fim", "Onde": "Volta à Ponte da Amizade", "Prédio": "",
                   "Chega às": d["horario_retorno"], "Atendido às": "", "Sai às": "", "O que comprar": ""})
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
        linhas.append({"Produto": it["nome"], "Prioridade": it["prioridade"], "Por quê": motivo})
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
        "declaracao": ("Sim: preencha a e-DBV antes de cruzar a Ponte e passe pela fila "
                       "\"bens a declarar\" na Receita."
                       if f["declaracao_necessaria"] else "Não precisa declarar."),
        "imposto_sem_cota": (None if sem_cota is None else
                             f"{fmt_usd(sem_cota)} ({fmt_brl(em_brl(sem_cota, cotacao))}). É o que você "
                             "pagaria se a Receita tirar a cota porque a bagagem passou de um limite "
                             "de unidades"),
        "alertas": f["alertas"],
        "avisos": f["avisos"],
        "premissa": f["premissa"],
        "data_referencia": fmt_data(f["data_referencia"]),
    }


def texto_solver(d: dict) -> str | None:
    """Aviso quando o modelo exato parou no tempo limite sem provar o ótimo (em
    linguagem simples: sem "ótimo" nem "gap" na tela)."""
    info = d.get("info", {})
    if info.get("status") not in (None, "otimo"):
        gap = info.get("gap")
        extra = (f" Pode existir um roteiro até {fmt_pct(gap)} melhor."
                 if isinstance(gap, (int, float)) else "")
        return f"Este é o melhor roteiro encontrado no tempo limite de cálculo.{extra}"
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
    return (f"O total a pagar ({fmt_usd(custo)}) passa do seu orçamento de {fmt_usd(orcamento)} "
            f"em {fmt_usd(excesso)}{extra}. Todos os itens foram mantidos na lista.")



def situacao_cota(d: dict) -> str:
    """Situação da cota com valores no formato brasileiro."""
    r = d["resumo"]
    if r["excedente"] <= 0:
        return "dentro da cota"
    return f"passa da cota em {fmt_usd(r['excedente'])} (imposto de {fmt_usd(r['imposto'])})"


def _imposto(gasto: float, inst: Instancia) -> float:
    return inst.aliquota * max(0.0, gasto - inst.cota)


LOJA_REFERENCIA = "CP-shopping-china"  # loja mais procurada pelos turistas (21/11/2026)


def comparativo_avulsa(d: dict, inst: Instancia, base: BaseApp,
                       loja_ref: str = LOJA_REFERENCIA, acrescimo: float = 0.0) -> dict | None:
    """Compra avulsa × roteiro do LesteShop (decidido em 21/11/2026).

    Compra avulsa = o turista compra tudo na loja de referência (Shopping China); o que
    ela não vende, ele paga pelo preço médio das lojas que vendem o item (média do menor
    preço de cada loja). O imposto de cada cenário é calculado sobre o gasto total
    (cota integral). Economia = (avulsa − roteiro) ÷ avulsa. ``None`` se nada foi comprado.

    Acréscimo da forma de pagamento (21/11/2026): ``inst`` já vem com os preços com a
    taxa (``pagamento.com_acrescimo``) e ``acrescimo`` aplica a mesma taxa aos preços da
    compra avulsa, que vêm da base."""
    comprados = [(p, c) for p in d["roteiro"] for c in p["compras"]]
    if not comprados:
        return None
    por_loja = base.ofertas.groupby(["produto_id", "loja_id"])["preco_usd"].min() * (1 + acrescimo)
    media = por_loja.groupby("produto_id").mean()
    lojas = base.lojas.set_index("loja_id")
    nome_ref = str(lojas.loc[loja_ref, "nome"]) if loja_ref in lojas.index else None
    no = {l.loja_id: i for i, l in enumerate(inst.lojas, start=1)}
    idx = {it.produto_id: k for k, it in enumerate(inst.itens)}
    linhas, na_media = [], []
    g_rota = g_avulsa = 0.0
    for p, c in comprados:
        k = idx[c["produto_id"]]
        q = inst.itens[k].quantidade
        preco_rota = inst.preco[(no[p["loja_id"]], k)]
        if nome_ref is not None and (c["produto_id"], loja_ref) in por_loja.index:
            preco_av, onde = float(por_loja[(c["produto_id"], loja_ref)]), nome_ref
        else:
            preco_av, onde = float(media[c["produto_id"]]), "preço médio das lojas"
            na_media.append(c["nome"])
        g_rota += preco_rota * q
        g_avulsa += preco_av * q
        linhas.append({"Produto": c["nome"], "Qtd.": q, "Roteiro: loja": p["nome"],
                       "Roteiro (US$)": fmt_usd(preco_rota * q), "Avulsa: onde": onde,
                       "Avulsa (US$)": fmt_usd(preco_av * q),
                       "Diferença (US$)": fmt_usd((preco_av - preco_rota) * q)})
    custo_rota = g_rota + _imposto(g_rota, inst)
    custo_avulsa = g_avulsa + _imposto(g_avulsa, inst)
    retorno_avulsa = None
    if nome_ref is not None and not na_media and loja_ref in no:
        retorno_avulsa = min_para_hhmm(agenda([no[loja_ref]], inst).retorno)
    return {
        "referencia": nome_ref or "preço médio das lojas",
        "tabela": pd.DataFrame(linhas),
        "na_media": na_media,
        "gasto_rota": g_rota, "gasto_avulsa": g_avulsa,
        "custo_rota": custo_rota, "custo_avulsa": custo_avulsa,
        "economia": custo_avulsa - custo_rota,
        # Fórmula da dona do projeto (21/11/2026): (avulsa − roteiro) / avulsa.
        "economia_pct": (custo_avulsa - custo_rota) / custo_avulsa if custo_avulsa > 0 else 0.0,
        "retorno_rota": d["horario_retorno"], "retorno_avulsa": retorno_avulsa,
        "lojas_rota": len(d["roteiro"]),
    }


def fmt_pct(valor: float) -> str:
    return f"{valor * 100:.1f}%".replace(".", ",")


# --- Fase 5: resumo no topo do resultado e mapa do roteiro --------------------------
def resumo_topo(d: dict, comparativo: dict | None, cotacao: Cotacao | None) -> list[dict]:
    """Os quatro números do topo do resultado (decidido em 21/11/2026): total a pagar,
    economia, hora de volta à Ponte e situação da cota. Cada um: rótulo, valor, detalhe."""
    r = d["resumo"]
    brl = em_brl(r["custo_total"], cotacao)
    total = {"rotulo": "Total a pagar", "valor": fmt_brl(brl) if brl is not None else fmt_usd(r["custo_total"]),
             "detalhe": (f"{fmt_usd(r['custo_total'])}, já com o imposto" if brl is not None
                         else "já com o imposto")}
    if comparativo is None:
        economia = {"rotulo": "Economia", "valor": "—", "detalhe": "nada foi comprado"}
    elif comparativo["economia"] > 0.005:
        e = comparativo["economia"]
        e_brl = em_brl(e, cotacao)
        economia = {"rotulo": "Você economiza", "valor": fmt_brl(e_brl) if e_brl is not None else fmt_usd(e),
                    "detalhe": f"{fmt_pct(comparativo['economia_pct'])} a menos que comprar tudo "
                               f"no {comparativo['referencia']}"}
    else:
        economia = {"rotulo": "Você economiza", "valor": fmt_brl(0.0) if cotacao is not None else fmt_usd(0.0),
                    "detalhe": f"nesta lista, o {comparativo['referencia']} sai pelo mesmo preço"}
    volta = {"rotulo": "Volta à Ponte", "valor": d["horario_retorno"],
             "detalhe": f"você queria sair até {d['horario_saida']}"}
    if r["excedente"] <= 0:
        cota = {"rotulo": "Cota da Receita", "valor": "Dentro da cota", "detalhe": "sem imposto a pagar"}
    else:
        cota = {"rotulo": "Cota da Receita", "valor": "Passa da cota",
                "detalhe": f"em {fmt_usd(r['excedente'])}: imposto de {fmt_usd(r['imposto'])}"}
    return [total, economia, volta, cota]


def _quando_e_o_que(p: dict) -> tuple[str, str]:
    horario = f"chega às {p['chegada']}, sai às {p['saida']}"
    if p["inicio_atendimento"] != p["chegada"]:
        horario = f"chega às {p['chegada']} (a loja abre às {p['inicio_atendimento']}), sai às {p['saida']}"
    return horario, ", ".join(f"{c['quantidade']}× {c['nome']}" for c in p["compras"])


def _rotulo_numeros(ordens: list[int]) -> str:
    """Rótulo curto do ponto no mapa: "3"; paradas seguidas "1-3"; senão "1,4"."""
    if len(ordens) > 1 and ordens == list(range(ordens[0], ordens[0] + len(ordens))):
        return f"{ordens[0]}-{ordens[-1]}"
    return ",".join(str(o) for o in ordens)


def dados_mapa(d: dict, inst: Instancia, base: BaseApp) -> dict | None:
    """Pontos e linhas do mapa do roteiro (sem Streamlit, para poder ser testado).

    Ponte da Amizade (partida e volta) + lojas numeradas na ordem da visita. Lojas no
    mesmo prédio (ou no mesmo endereço) viram um ponto só, com os números juntos
    ("1-3"), para os números não ficarem um em cima do outro.
    As linhas ligam as paradas em reta: não seguem as ruas. ``None`` se não há roteiro
    ou faltam coordenadas."""
    if not d["roteiro"]:
        return None
    p0 = base.pontos[base.pontos["id"].astype(int) == 0]
    if p0.empty:
        return None
    ponte = (float(p0.iloc[0]["latitude"]), float(p0.iloc[0]["longitude"]))
    coords = {l.loja_id: (l.latitude, l.longitude) for l in inst.lojas}
    if any(p["loja_id"] not in coords for p in d["roteiro"]):
        return None

    grupos: dict[object, list[dict]] = {}
    caminho = [ponte]
    for p in d["roteiro"]:
        lat, lon = coords[p["loja_id"]]
        chave = p["predio"] if p.get("predio") else (round(lat, 6), round(lon, 6))
        grupos.setdefault(chave, []).append(p)
        caminho.append((lat, lon))
    caminho.append(ponte)

    pontos = [{"lat": ponte[0], "lon": ponte[1], "numero": "P", "tipo": "ponte",
               "nome": "Ponte da Amizade (lado paraguaio)",
               "horario": f"saída às {d['horario_chegada']}, volta às {d['horario_retorno']}",
               "comprar": "começo e fim do passeio"}]
    for paradas in grupos.values():
        numeros = [str(p["ordem"]) for p in paradas]
        textos = [_quando_e_o_que(p) for p in paradas]
        lat = sum(coords[p["loja_id"]][0] for p in paradas) / len(paradas)
        lon = sum(coords[p["loja_id"]][1] for p in paradas) / len(paradas)
        predio = paradas[0].get("predio")
        pontos.append({
            "lat": lat, "lon": lon, "tipo": "loja",
            "numero": _rotulo_numeros([p["ordem"] for p in paradas]),
            "nome": (f"{predio}: " if predio and len(paradas) > 1 else "")
                    + " / ".join(f"{n}. {p['nome']}" for n, p in zip(numeros, paradas)),
            "horario": " / ".join(h for h, _ in textos),
            "comprar": " / ".join(c for _, c in textos),
        })
    trechos = [{"de": caminho[i], "para": caminho[i + 1]} for i in range(len(caminho) - 1)]
    lats = [c[0] for c in caminho]
    lons = [c[1] for c in caminho]
    return {"pontos": pd.DataFrame(pontos), "trechos": trechos,
            "centro": ((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2),
            "extensao": max(max(lats) - min(lats), max(lons) - min(lons))}


def texto_pagamento(forma_nome: str, acrescimo: float, custo: float, custo_dinheiro: float,
                    cotacao: Cotacao | None) -> str:
    """Quanto a forma de pagamento custa a mais que pagar em dinheiro (com o imposto)."""
    if acrescimo == 0:
        return f"Pagando em **{forma_nome.lower()}**: sem acréscimo."
    extra = custo - custo_dinheiro
    brl = em_brl(extra, cotacao)
    em_reais = f" ({fmt_brl(brl)})" if brl is not None else ""
    pct = f"{acrescimo * 100:g}".replace(".", ",")
    return (f"Pagando com **{forma_nome}** (+{pct}% nos preços): você paga "
            f"**{fmt_usd(extra)}{em_reais} a mais** do que pagando em dinheiro, já contando o "
            "imposto sobre o valor maior da nota.")
