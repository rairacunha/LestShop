"""Interface Streamlit do LesteShop (Fase 4).

Rodar na raiz do projeto::

    streamlit run app.py

Uma página só: barra lateral com a origem dos dados, a cotação e os dados da
viagem; no centro, a lista de compras, o botão de cálculo e o resultado.
"""

from __future__ import annotations

import datetime as dt

import streamlit as st

from ..otimizacao import config as config_otim
from ..otimizacao.resolver import resolver
from ..otimizacao.solucao import descrever
from . import apresentacao as ap
from . import base as base_app
from .pedido import ErroPedido, ItemPedido, montar_pedido, validar_pedido

LEGENDA_PRIORIDADE = {1: "1 · tanto faz", 2: "2 · pouco", 3: "3 · médio", 4: "4 · muito", 5: "5 · essencial"}


@st.cache_resource(show_spinner="Carregando a base de ofertas…")
def _base() -> base_app.BaseApp:
    return base_app.carregar_base()


@st.cache_data(ttl=3600, show_spinner=False)
def _cotacao():
    return base_app.cotacao_para_exibir()


def _estado() -> None:
    st.session_state.setdefault("lista", [])          # produto_ids, na ordem em que entraram
    st.session_state.setdefault("resultado", None)    # (assinatura, descrever(), Instancia)


def _remover(pid: str) -> None:
    st.session_state["lista"].remove(pid)
    for chave in (f"qtd_{pid}", f"pri_{pid}"):
        st.session_state.pop(chave, None)


def _adicionar() -> None:
    pid = st.session_state.get("novo_produto")
    if not pid:
        return
    if pid in st.session_state["lista"]:
        st.session_state["msg_lista"] = "Este produto já está na lista: ajuste a quantidade abaixo."
    else:
        st.session_state["lista"].append(pid)
        st.session_state[f"qtd_{pid}"] = 1
        st.session_state[f"pri_{pid}"] = 3
    st.session_state["novo_produto"] = None


def _barra_lateral(base: base_app.BaseApp, cotacao) -> tuple[dt.time, dt.time, float | None]:
    with st.sidebar:
        st.header("Origem dos dados")
        nivel, texto = ap.texto_origem(base)
        (st.success if nivel == "ok" else st.warning)(texto)
        if cotacao is None:
            st.caption("Cotação do dólar indisponível: valores só em US$.")
        else:
            valor = f"{cotacao.valor_brl_por_usd:.4f}".replace(".", ",")
            st.caption(f"Cotação: US$ 1 = R$ {valor} "
                       f"({ap.fmt_data(cotacao.data)}, {cotacao.fonte}). O R$ é só para referência.")
        if st.button("Recarregar base"):
            _base.clear()
            base_app.carregar_base(recriar=True)
            st.session_state["resultado"] = None
            st.rerun()

        st.header("Dados da viagem")
        st.caption("Horários no lado paraguaio, depois de atravessar a Ponte da Amizade.")
        chegada = st.time_input("Chegada", dt.time(8, 0), step=900, key="chegada")
        saida = st.time_input("Saída (volta à Ponte)", dt.time(16, 0), step=900, key="saida")
        orcamento = None
        if st.checkbox("Tenho um orçamento", key="tem_orcamento"):
            orcamento = float(st.number_input("Orçamento (US$)", min_value=1.0, value=500.0,
                                              step=50.0, key="orcamento"))
            if cotacao is not None:
                st.caption(f"≈ {ap.fmt_brl(ap.em_brl(orcamento, cotacao))}")
        else:
            st.caption("Sem orçamento: o app usa como teto a cota de isenção.")
    return chegada, saida, orcamento


def _lista_de_compras(base: base_app.BaseApp) -> list[ItemPedido]:
    st.subheader("1. Lista de compras")
    nomes = dict(zip(base.produtos["produto_id"], base.produtos["nome"]))
    categorias = dict(zip(base.produtos["produto_id"], base.produtos["categoria"]))

    def rotulo(pid: str) -> str:
        cat = categorias.get(pid)
        return f"{nomes[pid]} ({cat})" if isinstance(cat, str) and cat else nomes[pid]

    st.selectbox("Buscar produto", options=list(nomes), index=None, format_func=rotulo,
                 placeholder="Digite parte do nome e escolha na lista…", key="novo_produto",
                 on_change=_adicionar)
    if msg := st.session_state.pop("msg_lista", None):
        st.info(msg)

    itens = []
    if not st.session_state["lista"]:
        st.caption("A lista está vazia. Escolha um produto acima para incluir.")
    for pid in list(st.session_state["lista"]):
        c1, c2, c3, c4 = st.columns([5, 2, 3, 1], vertical_alignment="bottom")
        c1.markdown(f"**{nomes.get(pid, pid)}**")
        qtd = c2.number_input("Quantidade", min_value=1, step=1, key=f"qtd_{pid}",
                              help="Mais de uma unidade é comprada junto, numa loja só.")
        pri = c3.selectbox("Prioridade", options=list(LEGENDA_PRIORIDADE), key=f"pri_{pid}",
                           format_func=LEGENDA_PRIORIDADE.get,
                           help="Quanto o item importa: os de prioridade maior ficam de fora por último.")
        c4.button("✕", key=f"rem_{pid}", help="Remover da lista", on_click=_remover, args=(pid,))
        itens.append(ItemPedido(pid, int(qtd), int(pri)))
    return itens


def _calcular(base, itens, chegada, saida, orcamento, assinatura) -> None:
    erros = validar_pedido(base, itens, chegada, saida, orcamento)
    if erros:
        for e in erros:
            st.error(e)
        return
    with st.spinner("Calculando o melhor roteiro… (pode levar até 1 minuto)"):
        try:
            inst = montar_pedido(base, itens, chegada, saida, orcamento)
        except (ErroPedido, ValueError) as e:
            st.error(str(e))
            return
        sol, _ = resolver(inst, r=config_otim.R_PADRAO)
        d = descrever(sol, inst)
        d["avisos"] = list(d["avisos"]) + base_app.ofertas_antigas(base, [it.produto_id for it in itens])
    st.session_state["resultado"] = (assinatura, d, inst)


def _resultado(base, d: dict, inst, cotacao) -> None:
    st.subheader("3. Resultado")
    if aviso := ap.texto_solver(d):
        st.info(aviso)

    cols = st.columns(3)
    for col, (rot, usd, brl) in zip(cols, ap.totais(d, cotacao)):
        col.metric(rot, usd)
        col.caption(brl)
    st.markdown(f"**Cota de isenção:** {d['situacao_cota']}.")

    st.markdown("#### Onde comprar cada item")
    itens = ap.tabela_itens(d, base, cotacao)
    if itens.empty:
        st.warning("Nenhum item pôde ser comprado com estes dados.")
    else:
        st.dataframe(itens, hide_index=True, use_container_width=True)

    st.markdown("#### Roteiro a pé")
    r = d["resumo"]
    st.caption(f"Tempo andando: cerca de {r['tempo_andando']:.0f} min. "
               "Os horários contam a caminhada, a espera pela abertura e o tempo em cada loja.")
    st.dataframe(ap.tabela_roteiro(d), hide_index=True, use_container_width=True)

    fora = ap.tabela_fora(d, inst)
    if not fora.empty:
        st.markdown("#### Itens deixados de fora")
        st.dataframe(fora, hide_index=True, use_container_width=True)

    st.markdown("#### Receita Federal: cota, limites e declaração")
    f = ap.resumo_fiscal(d, cotacao)
    for alerta in f["alertas"]:
        st.warning(alerta)
    st.markdown(f"- **Cota:** {f['cota']}.\n"
                f"- **Situação:** {f['situacao_cota']}.\n"
                f"- **Declaração (e-DBV):** {f['declaracao']}")
    if f["imposto_sem_cota"]:
        st.markdown(f"- **Imposto sem a cota:** {f['imposto_sem_cota']}.")
    limites = ap.tabela_limites(d["fiscal"])
    if not limites.empty:
        with st.expander("Limites de quantidade da bagagem"):
            st.dataframe(limites, hide_index=True, use_container_width=True)
    st.caption(f"Premissa: {f['premissa']} Regras em vigor em {f['data_referencia']}.")

    avisos = list(d["avisos"]) + list(f["avisos"])
    if avisos:
        with st.expander(f"Avisos ({len(avisos)})"):
            for a in avisos:
                st.markdown(f"- {a}")


def main() -> None:
    st.set_page_config(page_title="LesteShop", page_icon="🛍️", layout="wide")
    _estado()
    base = _base()
    cotacao = _cotacao()

    st.title("LesteShop")
    st.caption("Onde comprar cada item em Ciudad del Este, o roteiro a pé a partir da Ponte da "
               "Amizade e a situação frente à cota da Receita Federal.")
    if base.origem != "real":
        st.warning(ap.texto_origem(base)[1])

    chegada, saida, orcamento = _barra_lateral(base, cotacao)
    itens = _lista_de_compras(base)

    st.subheader("2. Calcular")
    assinatura = (tuple((i.produto_id, i.quantidade, i.prioridade) for i in itens),
                  chegada, saida, orcamento)
    if st.button("Calcular roteiro", type="primary", disabled=not itens):
        _calcular(base, itens, chegada, saida, orcamento, assinatura)

    res = st.session_state["resultado"]
    if res is not None:
        if res[0] != assinatura:
            st.info("A lista ou os dados da viagem mudaram: clique em **Calcular roteiro** de novo.")
        else:
            _resultado(base, res[1], res[2], cotacao)
