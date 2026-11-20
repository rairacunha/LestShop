"""Interface Streamlit do LesteShop (Fase 4).

Rodar na raiz do projeto::

    streamlit run app.py

Uma página só: barra lateral com a fonte dos preços, a cotação e os dados da
viagem; no centro, a lista de compras, o botão de cálculo e o resultado.

Fontes dos preços:

* **Consulta ao Compras Paraguai** (padrão): o menu vem do catálogo curado
  (``data/catalogo_app.json``); ao calcular, só os itens da lista são consultados no
  site (``lesteshop.consulta``, cache de 6 h). Precisa rodar num computador com tela:
  se o site pedir a verificação anti-robô, a pessoa a resolve na janela que abrir.
* **Base guardada**: a base do SQLite (coletas salvas ou a base fictícia).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from ..consulta import busca
from ..consulta.cache import CacheConsulta
from ..consulta.catalogo import carregar_catalogo_app
from ..data.catalogo import IndiceCatalogo
from ..otimizacao import config as config_otim
from ..otimizacao.resolver import resolver
from ..otimizacao.solucao import descrever
from . import apresentacao as ap
from . import base as base_app
from .pedido import ErroPedido, ItemPedido, montar_pedido, validar_pedido

LEGENDA_PRIORIDADE = {1: "1 · tanto faz", 2: "2 · pouco", 3: "3 · médio", 4: "4 · muito", 5: "5 · essencial"}
MODO_CONSULTA = "Consulta ao Compras Paraguai"
MODO_BASE = "Base guardada"


@st.cache_resource(show_spinner="Carregando a base de ofertas…")
def _base() -> base_app.BaseApp:
    return base_app.carregar_base()


@st.cache_data(ttl=3600, show_spinner=False)
def _cotacao():
    return base_app.cotacao_para_exibir()


@st.cache_data(show_spinner=False)
def _catalogo():
    return carregar_catalogo_app()


def _estado() -> None:
    st.session_state.setdefault("lista", [])          # ids (catálogo ou produto), na ordem
    st.session_state.setdefault("resultado", None)    # dict com assinatura, descrever(), Instancia, base...


def _limpar_lista() -> None:
    for pid in st.session_state.get("lista", []):
        for chave in (f"qtd_{pid}", f"pri_{pid}"):
            st.session_state.pop(chave, None)
    st.session_state["lista"] = []
    st.session_state["resultado"] = None


def _remover(pid: str) -> None:
    st.session_state["lista"].remove(pid)
    for chave in (f"qtd_{pid}", f"pri_{pid}"):
        st.session_state.pop(chave, None)


def _adicionar(pid: str) -> None:
    if pid in st.session_state["lista"]:
        st.session_state["msg_lista"] = "Este produto já está na lista: ajuste a quantidade abaixo."
    else:
        st.session_state["lista"].append(pid)
        st.session_state[f"qtd_{pid}"] = 1
        st.session_state[f"pri_{pid}"] = 3


@st.cache_resource(show_spinner=False)
def _indice(rotulos: tuple[tuple[str, str], ...]) -> IndiceCatalogo:
    """Índice de busca (palavras em qualquer ordem, sem acento, início de palavra)."""
    return IndiceCatalogo(pd.DataFrame(rotulos, columns=["id", "nome"]))


def _cotacao_para(modo: str):
    """Cotação mostrada (decidido em 20/11/2026): a do Compras Paraguai, tirada das
    ofertas; sem ofertas reais, a PTAX (ou, na base fictícia, a cotação de teste)."""
    r = st.session_state.get("resultado")
    if r is not None and r.get("cotacao") is not None and r["assinatura"][0] == modo:
        return r["cotacao"]
    if modo == MODO_BASE or _base().origem == "real":
        base = _base()
        if base.origem == "real" and (c := base_app.cotacao_do_site(base.ofertas)) is not None:
            return c
        if modo == MODO_BASE:
            return _cotacao()
    c = _cotacao()
    return None if c is not None and "fictíc" in c.fonte.lower() else c


def _barra_lateral() -> tuple:
    with st.sidebar:
        st.header("Fonte dos preços")
        modo = st.radio("Fonte dos preços", [MODO_CONSULTA, MODO_BASE], key="modo",
                        label_visibility="collapsed", on_change=_limpar_lista)
        cotacao = _cotacao_para(modo)
        if modo == MODO_CONSULTA:
            st.info("Ao calcular, o app consulta no Compras Paraguai **só os itens da sua lista** "
                    "(preços guardados por 6 h). Se o site pedir a verificação de humano, "
                    "resolva-a na janela do navegador que abrir.")
            if st.button("Apagar preços guardados"):
                CacheConsulta().limpar()
                st.session_state["resultado"] = None
                st.toast("Preços guardados apagados: a próxima consulta vai ao site.")
        else:
            base = _base()
            nivel, texto = ap.texto_origem(base)
            (st.success if nivel == "ok" else st.warning)(texto)
            if st.button("Recarregar base"):
                _base.clear()
                base_app.carregar_base(recriar=True)
                st.session_state["resultado"] = None
                st.rerun()
        if cotacao is None:
            st.caption("Cotação do dólar indisponível: valores só em US$.")
        else:
            valor = f"{cotacao.valor_brl_por_usd:.4f}".replace(".", ",")
            st.caption(f"Cotação: US$ 1 = R$ {valor} "
                       f"({ap.fmt_data(cotacao.data)}, {cotacao.fonte}). O R$ é só para referência.")

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
    return modo, chegada, saida, orcamento, cotacao


def _opcoes(modo: str) -> dict[str, str]:
    """id -> rótulo do menu suspenso."""
    if modo == MODO_CONSULTA:
        return {it.id: it.rotulo for it in _catalogo()}
    base = _base()
    rotulos = {}
    for r in base.produtos.itertuples():
        rotulos[r.produto_id] = f"{r.nome} ({r.categoria})" if isinstance(r.categoria, str) and r.categoria else r.nome
    return rotulos


def _lista_de_compras(opcoes: dict[str, str]) -> list[tuple[str, int, int]]:
    st.subheader("1. Lista de compras")
    texto = st.text_input("Buscar produto", key="busca_produto",
                          placeholder="Digite palavras do nome (em qualquer ordem) e aperte Enter. Ex.: iphone 17")
    if texto.strip():
        achados = _indice(tuple(opcoes.items())).sugerir(texto, limite=8)
        if achados.empty:
            st.caption("Nenhum produto encontrado. Tente menos palavras ou só a marca.")
        for r in achados.itertuples():
            c1, c2 = st.columns([8, 2], vertical_alignment="center")
            c1.write(r.nome)
            ja = r.id in st.session_state["lista"]
            c2.button("Na lista" if ja else "Adicionar", key=f"add_{r.id}", disabled=ja,
                      on_click=_adicionar, args=(r.id,), width="stretch")
    if msg := st.session_state.pop("msg_lista", None):
        st.info(msg)

    pedidos = []
    if not st.session_state["lista"]:
        st.caption("A lista está vazia. Busque um produto acima e clique em Adicionar.")
    else:
        st.markdown("**Sua lista**")
    for pid in list(st.session_state["lista"]):
        c1, c2, c3, c4 = st.columns([5, 2, 3, 1], vertical_alignment="bottom")
        c1.markdown(f"**{opcoes.get(pid, pid)}**")
        qtd = c2.number_input("Quantidade", min_value=1, step=1, key=f"qtd_{pid}",
                              help="Mais de uma unidade é comprada junto, numa loja só.")
        pri = c3.selectbox("Prioridade", options=list(LEGENDA_PRIORIDADE), key=f"pri_{pid}",
                           format_func=LEGENDA_PRIORIDADE.get,
                           help="Quanto o item importa: os de prioridade maior ficam de fora por último.")
        c4.button("✕", key=f"rem_{pid}", help="Remover da lista", on_click=_remover, args=(pid,))
        pedidos.append((pid, int(qtd), int(pri)))
    return pedidos


def _otimizar(base, itens, chegada, saida, orcamento, categorias=None):
    erros = validar_pedido(base, itens, chegada, saida, orcamento)
    if erros:
        for e in erros:
            st.error(e)
        return None
    with st.spinner("Calculando o melhor roteiro…"):
        try:
            inst = montar_pedido(base, itens, chegada, saida, orcamento, categorias=categorias)
        except (ErroPedido, ValueError) as e:
            st.error(str(e))
            return None
        sol, _ = resolver(inst, r=config_otim.R_PADRAO)
        d = descrever(sol, inst)
        d["avisos"] = (list(d["avisos"]) + base_app.ofertas_antigas(base, [it.produto_id for it in itens])
                       + [a for it in itens for a in base.avisos_produto.get(it.produto_id, [])])
    return d, inst


def _calcular_base(pedidos, chegada, saida, orcamento) -> dict | None:
    base = _base()
    r = _otimizar(base, [ItemPedido(*p) for p in pedidos], chegada, saida, orcamento)
    return None if r is None else {"d": r[0], "inst": r[1], "base": base, "consulta": None,
                                   "cotacao": base_app.cotacao_do_site(base.ofertas) if base.origem == "real" else None}


def _calcular_consulta(pedidos, chegada, saida, orcamento) -> dict | None:
    if hhmm(saida) <= hhmm(chegada):
        st.error("O horário de saída deve ser depois do horário de chegada.")
        return None
    cat = {it.id: it for it in _catalogo()}
    itens_cat = [cat[pid] for pid, _, _ in pedidos]
    with st.status("Consultando preços no Compras Paraguai…", expanded=True) as status:
        res = busca.consultar(itens_cat, busca.criar_cliente_navegador, progresso=status.write)
        status.update(label=f"Consulta concluída ({res.requisicoes} acesso(s) ao site; "
                            f"{len(res.do_cache)} item(ns) com preços guardados).",
                      state="complete", expanded=False)
    for aviso in res.avisos:
        st.warning(aviso)
    itens = [ItemPedido(res.por_item[pid], q, p) for pid, q, p in pedidos if pid in res.por_item]
    if not itens:
        st.error("Nenhum item da lista foi encontrado no Compras Paraguai.")
        return None
    base = busca.para_base(res)
    r = _otimizar(base, itens, chegada, saida, orcamento, categorias=busca.mapa_categorias(itens_cat, res))
    if r is None:
        return None
    r[0]["avisos"] = list(r[0]["avisos"]) + list(res.avisos)
    return {"d": r[0], "inst": r[1], "base": base, "cotacao": base_app.cotacao_do_site(base.ofertas),
            "consulta": {"res": res, "nao_encontrados": [cat[i].nome for i in res.nao_encontrados]}}


def hhmm(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def _matriz(res) -> pd.DataFrame:
    m = res.matriz()
    if m.empty:
        return m
    larga = m.pivot_table(index="produto", columns="loja", values="preco_usd", aggfunc="min")
    return larga.map(lambda v: "" if pd.isna(v) else ap.fmt_usd(v))


def _resultado(r: dict, cotacao) -> None:
    d, inst, base, consulta = r["d"], r["inst"], r["base"], r["consulta"]
    st.subheader("3. Resultado")
    if consulta is not None:
        res = consulta["res"]
        momentos = sorted(res.consultado_em.values())
        quando = (f"{ap.fmt_data(momentos[0])} {momentos[0][11:16]}" if momentos else "—")
        st.success(f"Preços do Compras Paraguai, consultados em {quando} (só os itens da lista).")
        if consulta["nao_encontrados"]:
            st.warning("Não encontrados no site: " + ", ".join(consulta["nao_encontrados"]) + ".")
    elif base.origem != "real":
        st.warning(ap.texto_origem(base)[1])
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
        st.dataframe(itens, hide_index=True, width="stretch")

    st.markdown("#### Roteiro a pé")
    st.caption(f"Tempo andando: cerca de {d['resumo']['tempo_andando']:.0f} min. "
               "Os horários contam a caminhada, a espera pela abertura e o tempo em cada loja.")
    st.dataframe(ap.tabela_roteiro(d), hide_index=True, width="stretch")

    fora = ap.tabela_fora(d, inst)
    if not fora.empty:
        st.markdown("#### Itens deixados de fora")
        st.dataframe(fora, hide_index=True, width="stretch")

    if consulta is not None:
        with st.expander("Preços encontrados (Produto × Loja, em US$)"):
            st.dataframe(_matriz(consulta["res"]), width="stretch")

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
            st.dataframe(limites, hide_index=True, width="stretch")
    st.caption(f"Premissa: {f['premissa']} Regras em vigor em {f['data_referencia']}.")

    avisos = list(d["avisos"]) + list(f["avisos"])
    if avisos:
        with st.expander(f"Avisos ({len(avisos)})"):
            for a in avisos:
                st.markdown(f"- {a}")


def main() -> None:
    st.set_page_config(page_title="LesteShop", page_icon="🛍️", layout="wide")
    _estado()

    st.title("LesteShop")
    st.caption("Onde comprar cada item em Ciudad del Este, o roteiro a pé a partir da Ponte da "
               "Amizade e a situação frente à cota da Receita Federal.")

    modo, chegada, saida, orcamento, cotacao = _barra_lateral()
    if modo == MODO_BASE and _base().origem != "real":
        st.warning(ap.texto_origem(_base())[1])
    pedidos = _lista_de_compras(_opcoes(modo))

    st.subheader("2. Calcular")
    assinatura = (modo, tuple(pedidos), chegada, saida, orcamento)
    if st.button("Calcular roteiro", type="primary", disabled=not pedidos):
        calcular = _calcular_consulta if modo == MODO_CONSULTA else _calcular_base
        r = calcular(pedidos, chegada, saida, orcamento)
        st.session_state["resultado"] = None if r is None else {**r, "assinatura": assinatura}

    r = st.session_state["resultado"]
    if r is not None:
        if r["assinatura"] != assinatura:
            st.info("A lista ou os dados da viagem mudaram: clique em **Calcular roteiro** de novo.")
        else:
            _resultado(r, r.get("cotacao") or cotacao)
