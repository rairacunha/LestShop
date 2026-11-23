"""Interface Streamlit do LesteShop (Fase 4; design da Fase 5).

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

Fase 5 (21/11/2026): tema azul e vermelho (``.streamlit/config.toml``), textos simples
para o turista, resumo no topo do resultado e mapa do roteiro (pydeck). O cálculo não
mudou. O logotipo entra quando existir ``assets/logo.png``.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from ..consulta import busca
from ..consulta.cache import CacheConsulta
from ..consulta.catalogo import ItemCatalogo, carregar_catalogo_app
from ..data import config as config_dados
from ..data.sources.http import ErroColeta
from ..data.sources.parser_cp import ErroEstruturaHTML
from ..data.catalogo import IndiceCatalogo
from ..otimizacao import config as config_otim
from ..otimizacao.resolver import resolver
from ..otimizacao.solucao import descrever
from . import apresentacao as ap
from . import base as base_app
from . import passeio as ps
from .pagamento import carregar_formas, com_acrescimo
from .pedido import ErroPedido, ItemPedido, montar_pedido, teto_sem_limite, validar_pedido

LEGENDA_PRIORIDADE = {1: "1 · tanto faz", 2: "2 · pouco", 3: "3 · médio", 4: "4 · muito", 5: "5 · essencial"}
# Lugar do logotipo (Fase 5): a dona do projeto vai criar o arquivo. Enquanto ele não
# existir, a tela fica só com o nome "LesteShop".
LOGO = Path(__file__).resolve().parents[3] / "assets" / "logo.png"
AZUL, VERMELHO, BRANCO, VERDE = [0, 56, 168], [213, 43, 30], [255, 255, 255], [0, 140, 70]
# Barra "economizar ↔ andar menos" (autorizada em 23/11/2026): valor de 1 minuto de
# caminhada (r, US$/min) no objetivo do modelo. O padrão continua US$ 0,25/min.
VALOR_MINUTO = {0.0: "Economizar ao máximo", 0.10: "Economizar", config_otim.R_PADRAO: "Equilíbrio",
                0.50: "Andar menos", 1.0: "Andar o mínimo"}

# Botão "Usar minha localização" (st.components.v2): pede a posição ao navegador. Só
# funciona se a pessoa permitir o acesso à localização.
_JS_LOCALIZACAO = """
export default function(component) {
    const { parentElement, setStateValue } = component;
    const botao = parentElement.querySelector('button');
    const aviso = parentElement.querySelector('span');
    botao.onclick = () => {
        if (!navigator.geolocation) {
            setStateValue('posicao', { erro: 'Este navegador não informa a localização.' });
            return;
        }
        aviso.textContent = 'Procurando sua localização…';
        navigator.geolocation.getCurrentPosition(
            (p) => { aviso.textContent = ''; setStateValue('posicao', {
                lat: p.coords.latitude, lon: p.coords.longitude,
                precisao: p.coords.accuracy, quando: Date.now() }); },
            (e) => { aviso.textContent = ''; setStateValue('posicao', {
                erro: e.code === 1 ? 'A localização está desativada ou o acesso foi negado.'
                                   : 'Não foi possível obter a localização.' }); },
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
    };
}
"""
_CSS_LOCALIZACAO = """
button { background: var(--st-primary-color); color: white; border: none; border-radius: 8px;
         padding: 0.5rem 1rem; font: inherit; cursor: pointer; }
span { margin-left: 0.75rem; color: var(--st-text-color); font: inherit; }
"""
MODO_CONSULTA = "Consulta ao Compras Paraguai"
MODO_BASE = "Base guardada"


def tem_tela() -> bool:
    """False num servidor sem tela (Streamlit Community Cloud, Codespaces): lá não há como
    abrir o navegador para a verificação anti-robô, então a consulta ao vivo é escondida.
    ``LESTESHOP_CONSULTA=0/1`` força a escolha."""
    forcado = os.environ.get("LESTESHOP_CONSULTA")
    if forcado in ("0", "1"):
        return forcado == "1"
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True  # Windows e Mac


def _assinatura_coletas() -> tuple:
    """Muda quando uma coleta ou consulta grava dados novos em data/coletas/."""
    pasta = config_dados.DIR_COLETAS
    if not pasta.exists():
        return ()
    return tuple(sorted((str(a), a.stat().st_mtime) for a in pasta.glob("*/*.csv")))


@st.cache_resource(show_spinner="Carregando a base de ofertas…", max_entries=1)
def _base_cache(_assinatura: tuple) -> base_app.BaseApp:
    return base_app.carregar_base(recriar=bool(_assinatura))


def _base() -> base_app.BaseApp:
    return _base_cache(_assinatura_coletas())


@st.cache_data(ttl=3600, show_spinner=False)
def _cotacao():
    return base_app.cotacao_para_exibir()


@st.cache_data(show_spinner=False)
def _formas():
    return carregar_formas()


@st.cache_data(show_spinner=False)
def _catalogo():
    return carregar_catalogo_app()


def _estado() -> None:
    st.session_state.setdefault("livres", {})       # id -> ItemCatalogo da busca livre no site
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


def _adicionar_modelo(modelo: dict, termo: str) -> None:
    """Modelo achado na busca do site (fora da base): entra na lista e, ao calcular, é
    consultado e gravado na base guardada."""
    pid = f"cp:{modelo['modelo_id']}"
    st.session_state["livres"][pid] = ItemCatalogo(pid, modelo["nome"], termo, "", modelo["url"])
    _adicionar(pid)


def _itens_catalogo() -> dict[str, ItemCatalogo]:
    """Itens que o modo Consulta oferece: catálogo curado + produtos reais já guardados
    na base (coletas e consultas anteriores) + modelos achados agora na busca do site."""
    itens = {it.id: it for it in _catalogo()}
    urls = {it.url_modelo for it in itens.values() if it.url_modelo}
    base = _base()
    for r in base.produtos.itertuples():
        url = r.url_modelo if isinstance(r.url_modelo, str) else None
        if url and url not in urls and str(r.tipo_dado) == "real":
            pid = "cp:" + str(r.produto_id).removeprefix("CP-")
            cat = r.categoria if isinstance(r.categoria, str) else ""
            itens[pid] = ItemCatalogo(pid, r.nome, r.nome, cat, url)
    return {**itens, **st.session_state.get("livres", {})}


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
        st.header("De onde vêm os preços")
        modos = [MODO_CONSULTA, MODO_BASE] if tem_tela() else [MODO_BASE]
        modo = st.radio("Fonte dos preços", modos, key="modo",
                        label_visibility="collapsed", on_change=_limpar_lista)
        if not tem_tela():
            st.caption("Na versão web, o app usa os preços já buscados no site Compras Paraguai. "
                       "A busca na hora só funciona no computador (o site pede para provar que "
                       "você não é um robô).")
        cotacao = _cotacao_para(modo)
        if modo == MODO_CONSULTA:
            st.info("Ao calcular, o app busca no site Compras Paraguai os preços **só dos produtos "
                    "da sua lista** e guarda o resultado por 6 horas. Se o site pedir para provar "
                    "que você não é um robô, responda na janela do navegador que abrir.")
            if st.button("Apagar preços guardados"):
                CacheConsulta().limpar()
                st.session_state["resultado"] = None
                st.toast("Preços guardados apagados: a próxima consulta vai ao site.")
        else:
            base = _base()
            nivel, texto = ap.texto_origem(base)
            (st.success if nivel == "ok" else st.warning)(texto)
            if st.button("Recarregar base"):
                _base_cache.clear()
                st.session_state["resultado"] = None
                st.rerun()
        if cotacao is None:
            st.caption("Cotação do dólar indisponível: valores só em US$.")
        else:
            valor = f"{cotacao.valor_brl_por_usd:.4f}".replace(".", ",")
            st.caption(f"Dólar: US$ 1 = R$ {valor} "
                       f"({ap.fmt_data(cotacao.data)}, {cotacao.fonte}). Os valores em R$ são "
                       "só para você ter uma ideia; as lojas cobram em dólar.")

        st.header("Sua viagem")
        st.caption("Horários do lado paraguaio, depois de atravessar a Ponte da Amizade.")
        chegada = st.time_input("Chego à Ponte às", dt.time(8, 0), step=900, key="chegada")
        saida = st.time_input("Quero voltar à Ponte até", dt.time(16, 0), step=900, key="saida")
        orcamento = None
        if st.checkbox("Tenho um orçamento", key="tem_orcamento"):
            orcamento = float(st.number_input("Orçamento (US$)", min_value=1.0, value=500.0,
                                              step=50.0, key="orcamento"))
            if cotacao is not None:
                st.caption(f"≈ {ap.fmt_brl(ap.em_brl(orcamento, cotacao))}")
            st.caption("O orçamento serve só de referência: todos os produtos continuam na lista "
                       "e o app avisa se o total passar dele.")
        else:
            st.caption("Sem orçamento: o app monta o roteiro com todos os produtos da lista.")

        formas = _formas()
        padrao = next(i for i, fp in enumerate(formas) if fp.padrao)
        forma = st.radio("Forma de pagamento", formas, index=padrao, key="forma_pagamento",
                         format_func=lambda fp: fp.rotulo)
        st.caption("Nas lojas, o preço muda com a forma de pagamento. Os acréscimos são "
                   "estimados (observação de campo, não vêm do site) e o imposto é calculado "
                   "sobre o valor com o acréscimo, que é o valor da nota.")

        st.header("Economizar ou andar menos?")
        r_min = st.select_slider("Prefiro", options=list(VALOR_MINUTO), value=config_otim.R_PADRAO,
                                 format_func=VALOR_MINUTO.get, key="valor_minuto",
                                 label_visibility="collapsed")
        st.caption(f"Para o lado **economizar**, o app aceita andar mais para achar preço menor; "
                   f"para o lado **andar menos**, aceita pagar um pouco mais para andar menos. "
                   f"(Cada minuto de caminhada vale {ap.fmt_usd(r_min)} na conta.)")
    return modo, chegada, saida, orcamento, cotacao, forma, r_min


def _opcoes(modo: str) -> dict[str, str]:
    """id -> rótulo do menu suspenso."""
    if modo == MODO_CONSULTA:
        return {pid: (it.rotulo if it.categoria else it.nome) for pid, it in _itens_catalogo().items()}
    base = _base()
    rotulos = {}
    for r in base.produtos.itertuples():
        rotulos[r.produto_id] = f"{r.nome} ({r.categoria})" if isinstance(r.categoria, str) and r.categoria else r.nome
    return rotulos


def _linha_resultado(nome: str, pid: str, ao_clicar, args) -> None:
    c1, c2 = st.columns([8, 2], vertical_alignment="center")
    c1.write(nome)
    ja = pid in st.session_state["lista"]
    c2.button("Na lista" if ja else "Adicionar", key=f"add_{pid}", disabled=ja,
              on_click=ao_clicar, args=args, width="stretch")


def _buscar_no_site(texto: str) -> None:
    """Produto que não está na base: procura no Compras Paraguai (1 página, cache 6 h)."""
    with st.spinner("Este produto ainda não está no app: procurando no Compras Paraguai… (se o "
                    "site pedir para provar que você não é um robô, responda na janela do navegador)"):
        try:
            modelos = busca.buscar_no_site(texto, busca.criar_cliente_navegador)
        except (ErroColeta, ErroEstruturaHTML) as e:
            st.error(f"Não foi possível procurar no Compras Paraguai: {e}")
            return
    if not modelos:
        st.caption("Nenhum produto encontrado, nem no app nem no Compras Paraguai. Tente outras palavras.")
        return
    st.caption("Ainda não estava no app. Encontrados no Compras Paraguai (ao calcular, o app "
               "busca os preços e guarda o produto para as próximas vezes):")
    for m in modelos:
        _linha_resultado(m["nome"], f"cp:{m['modelo_id']}", _adicionar_modelo, (m, texto))


def _lista_de_compras(opcoes: dict[str, str]) -> list[tuple[str, int, int]]:
    st.subheader("1. O que você quer comprar")
    consulta = st.session_state.get("modo") == MODO_CONSULTA
    texto = st.text_input("Buscar produto", key="busca_produto",
                          placeholder="Digite palavras do nome (em qualquer ordem) e aperte Enter. Ex.: iphone 17")
    if texto.strip():
        achados = _indice(tuple(opcoes.items())).sugerir(texto, limite=8)
        for r in achados.itertuples():
            _linha_resultado(r.nome, r.id, _adicionar, (r.id,))
        if achados.empty and not consulta:
            st.caption("Nenhum produto encontrado. Tente menos palavras ou só a marca.")
        elif achados.empty:
            _buscar_no_site(texto)
    if msg := st.session_state.pop("msg_lista", None):
        st.info(msg)

    pedidos = []
    if not st.session_state["lista"]:
        st.caption("A lista está vazia. Busque um produto acima e clique em Adicionar.")
    else:
        st.markdown("**Sua lista**")
        st.caption("**Prioridade:** diz o que é mais importante para você. Se não der tempo de "
                   "passar em todas as lojas, o app mantém primeiro os produtos de prioridade maior.")
    for pid in list(st.session_state["lista"]):
        c1, c2, c3, c4 = st.columns([5, 2, 3, 1], vertical_alignment="bottom")
        c1.markdown(f"**{opcoes.get(pid, pid)}**")
        qtd = c2.number_input("Quantidade", min_value=1, step=1, key=f"qtd_{pid}",
                              help="Mais de uma unidade é comprada junto, numa loja só.")
        pri = c3.selectbox("Prioridade", options=list(LEGENDA_PRIORIDADE), key=f"pri_{pid}",
                           format_func=LEGENDA_PRIORIDADE.get,
                           help="Se não der tempo de passar em todas as lojas, os produtos de "
                                "prioridade maior ficam na lista.")
        c4.button("✕", key=f"rem_{pid}", help="Remover da lista", on_click=_remover, args=(pid,))
        pedidos.append((pid, int(qtd), int(pri)))
    return pedidos


def _otimizar(base, itens, chegada, saida, orcamento, r_min, categorias=None):
    erros = validar_pedido(base, itens, chegada, saida, orcamento)
    if erros:
        for e in erros:
            st.error(e)
        return None
    with st.spinner("Procurando o melhor roteiro para você…"):
        try:
            inst = montar_pedido(base, itens, chegada, saida, teto_sem_limite(base, itens),
                                 categorias=categorias)
        except (ErroPedido, ValueError) as e:
            st.error(str(e))
            return None
        sol, _ = resolver(inst, r=r_min)
        d = descrever(sol, inst)
        d["avisos"] = (list(d["avisos"]) + base_app.ofertas_antigas(base, [it.produto_id for it in itens])
                       + [a for it in itens for a in base.avisos_produto.get(it.produto_id, [])])
    return d, inst, sol


def _calcular_base(pedidos, chegada, saida, orcamento, r_min) -> dict | None:
    base = _base()
    r = _otimizar(base, [ItemPedido(*p) for p in pedidos], chegada, saida, orcamento, r_min)
    return None if r is None else {"d": r[0], "inst": r[1], "sol": r[2], "base": base, "consulta": None,
                                   "cotacao": base_app.cotacao_do_site(base.ofertas) if base.origem == "real" else None}


def _calcular_consulta(pedidos, chegada, saida, orcamento, r_min) -> dict | None:
    if hhmm(saida) <= hhmm(chegada):
        st.error("O horário de saída deve ser depois do horário de chegada.")
        return None
    cat = _itens_catalogo()
    itens_cat = [cat[pid] for pid, _, _ in pedidos]
    with st.status("Buscando os preços no Compras Paraguai…", expanded=True) as status:
        res = busca.consultar(itens_cat, busca.criar_cliente_navegador, progresso=status.write,
                              dir_coletas=config_dados.DIR_COLETAS)
        status.update(label=f"Preços encontrados ({res.requisicoes} acesso(s) ao site; "
                            f"{len(res.do_cache)} produto(s) com preços guardados de antes).",
                      state="complete", expanded=False)
    for aviso in res.avisos:
        st.warning(aviso)
    itens = [ItemPedido(res.por_item[pid], q, p) for pid, q, p in pedidos if pid in res.por_item]
    if not itens:
        st.error("Nenhum produto da lista foi encontrado no Compras Paraguai.")
        return None
    base = busca.para_base(res)
    r = _otimizar(base, itens, chegada, saida, orcamento, r_min,
                  categorias=busca.mapa_categorias(itens_cat, res))
    if r is None:
        return None
    r[0]["avisos"] = list(r[0]["avisos"]) + list(res.avisos)
    return {"d": r[0], "inst": r[1], "sol": r[2], "base": base, "cotacao": base_app.cotacao_do_site(base.ofertas),
            "consulta": {"res": res, "nao_encontrados": [cat[i].nome for i in res.nao_encontrados]}}


def hhmm(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def _matriz(res) -> pd.DataFrame:
    m = res.matriz()
    if m.empty:
        return m
    larga = m.pivot_table(index="produto", columns="loja", values="preco_usd", aggfunc="min")
    return larga.map(lambda v: "" if pd.isna(v) else ap.fmt_usd(v))


def _valor(usd: float, cotacao) -> str:
    """Em R$ (cotação do site), ou em US$ se não houver cotação."""
    brl = ap.em_brl(usd, cotacao)
    return ap.fmt_brl(brl) if brl is not None else ap.fmt_usd(usd)


def _comparativo(c: dict | None, cotacao) -> None:
    """Compra avulsa (Shopping China) × roteiro do LesteShop."""
    if c is None:
        return
    st.markdown("#### Quanto você economiza")
    st.caption(f"Comparação com a **compra avulsa**: comprar tudo numa loja só, o {c['referencia']}, "
               "a mais procurada pelos turistas.")
    if c["na_media"]:
        st.info(f"O {c['referencia']} não vende: {', '.join(c['na_media'])}. Para comparar, esses "
                "produtos entram pelo preço médio das lojas.")
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Tudo no {c['referencia']}", _valor(c["custo_avulsa"], cotacao))
    volta = f" · volta à Ponte às {c['retorno_avulsa']}" if c["retorno_avulsa"] else ""
    c1.caption(f"{ap.fmt_usd(c['custo_avulsa'])}{volta}")
    c2.metric(f"Seu roteiro ({c['lojas_rota']} loja{'s' if c['lojas_rota'] > 1 else ''})",
              _valor(c["custo_rota"], cotacao))
    c2.caption(f"{ap.fmt_usd(c['custo_rota'])} · volta à Ponte às {c['retorno_rota']}")
    if c["economia"] > 0.005:
        c3.metric("Você economiza", _valor(c["economia"], cotacao),
                  delta=f"{ap.fmt_pct(c['economia_pct'])} a menos")
        c3.caption("Economia = (compra avulsa − seu roteiro) ÷ compra avulsa.")
    else:
        c3.metric("Você economiza", _valor(0.0, cotacao))
        c3.caption("Nesta lista, comprar tudo numa loja só não sairia mais caro.")
    st.caption("Os dois valores já incluem o imposto da Receita.")
    with st.expander("Preço de cada produto nos dois casos"):
        st.dataframe(c["tabela"], hide_index=True, width="stretch")


def _resumo(cartoes: list[dict]) -> None:
    """Os quatro números do topo do resultado, num quadro com borda."""
    with st.container(border=True):
        for col, c in zip(st.columns(len(cartoes)), cartoes):
            col.metric(c["rotulo"], c["valor"])
            col.caption(c["detalhe"])


def _zoom(extensao_graus: float) -> float:
    """Zoom do mapa para caber todas as paradas (Ciudad del Este: poucos quarteirões)."""
    if extensao_graus <= 0:
        return 16.0
    return max(12.0, min(17.0, math.log2(360 / extensao_graus) - 0.9))


def _mapa(m: dict | None, passeio: bool = False) -> None:
    """Mapa do roteiro (pydeck, mapa de fundo gratuito da CARTO, sem chave)."""
    if m is None:
        st.caption("Mapa indisponível: faltam as coordenadas de alguma loja.")
        return
    import pydeck as pdk

    pontos = m["pontos"].copy()
    pontos["cor"] = [{"ponte": VERMELHO, "voce": VERDE}.get(t, AZUL) for t in pontos["tipo"]]
    pontos["raio"] = [12 + 3 * (len(n) - 1) for n in pontos["numero"]]
    trechos = pd.DataFrame([{"de": [t["de"][1], t["de"][0]], "para": [t["para"][1], t["para"][0]]}
                            for t in m["trechos"]])
    camadas = [
        pdk.Layer("LineLayer", trechos, get_source_position="de", get_target_position="para",
                  get_color=AZUL + [170], get_width=4),
        pdk.Layer("ScatterplotLayer", pontos, get_position=["lon", "lat"], get_fill_color="cor",
                  get_radius="raio", radius_units="'pixels'", stroked=True, get_line_color=BRANCO,
                  line_width_min_pixels=2, pickable=True),
        pdk.Layer("TextLayer", pontos, get_position=["lon", "lat"], get_text="numero", get_size=13,
                  get_color=BRANCO, font_weight=700, get_text_anchor="'middle'",
                  get_alignment_baseline="'center'"),
    ]
    lat, lon = m["centro"]
    deck = pdk.Deck(
        layers=camadas, map_provider="carto", map_style="light",
        initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=_zoom(m["extensao"])),
        tooltip={"html": "<b>{nome}</b><br/>{horario}<br/><b>Comprar:</b> {comprar}",
                 "style": {"backgroundColor": "#0038A8", "color": "white", "fontSize": "13px"}},
    )
    st.pydeck_chart(deck, height=440)
    inicio = "🟢 **V** = você, agora · 🔴 **P** = Ponte da Amizade (volta)" if passeio else \
        "🔴 **P** = Ponte da Amizade (saída e volta)"
    st.caption(f"{inicio} · 🔵 números = lojas, na ordem da visita "
               "(\"1-3\" = paradas 1 a 3, no mesmo prédio). "
               "Passe o mouse num ponto para ver o horário e o que comprar. As linhas ligam as "
               "paradas em linha reta: **não mostram o caminho pelas ruas**.")


def _origem_dos_precos(base, consulta) -> None:
    if consulta is not None:
        res = consulta["res"]
        momentos = sorted(res.consultado_em.values())
        quando = (f"{ap.fmt_data(momentos[0])} {momentos[0][11:16]}" if momentos else "—")
        st.success(f"Preços do Compras Paraguai, consultados em {quando} (só os produtos da sua lista).")
        if consulta["nao_encontrados"]:
            st.warning("Não encontrados no site: " + ", ".join(consulta["nao_encontrados"]) + ".")
    elif base.origem != "real":
        st.warning(ap.texto_origem(base)[1])


def _receita_federal(d: dict, inst, cotacao) -> dict:
    st.markdown("#### Receita Federal: cota e declaração")
    f = ap.resumo_fiscal(d, cotacao)
    st.caption(f"**O que é a cota:** na volta, cada pessoa pode trazer até "
               f"{ap.fmt_usd(inst.cota)} em compras sem pagar imposto. Sobre o que passar disso, "
               f"a Receita cobra {ap.fmt_pct(inst.aliquota)} de imposto.")
    for alerta in f["alertas"]:
        st.warning(alerta)
    st.markdown(f"- **Sua situação:** {f['situacao_cota']}.\n"
                f"- **Precisa declarar?** {f['declaracao']}")
    if f["imposto_sem_cota"]:
        st.markdown(f"- **Imposto sem a cota:** {f['imposto_sem_cota']}.")
    st.caption("**O que é a e-DBV:** a declaração de bens do viajante, feita pela internet "
               "(site ou aplicativo da Receita) antes de passar pela fiscalização.")
    limites = ap.tabela_limites(d["fiscal"])
    if not limites.empty:
        with st.expander("Limites de quantidade da bagagem"):
            st.dataframe(limites, hide_index=True, width="stretch")
    st.caption(f"Regra usada: {f['cota']}. {f['premissa']} Regras em vigor em {f['data_referencia']}.")
    return f


def _com_forma(r: dict, forma) -> tuple[dict, object]:
    """Refaz os valores do roteiro já escolhido com o acréscimo da forma de pagamento
    (o roteiro e as lojas não mudam; o imposto é sobre o valor com o acréscimo)."""
    if forma.acrescimo == 0:
        return r["d"], r["inst"]
    inst = com_acrescimo(r["inst"], forma.acrescimo)
    d = descrever(r["sol"], inst)
    d["avisos"] = r["d"]["avisos"]
    return d, inst


def _resultado(r: dict, cotacao, forma) -> None:
    base, consulta = r["base"], r["consulta"]
    d, inst = _com_forma(r, forma)
    st.subheader("3. Seu resultado")
    _origem_dos_precos(base, consulta)
    if aviso := ap.texto_solver(d):
        st.info(aviso)
    if aviso := ap.aviso_orcamento(d, r.get("orcamento"), cotacao):
        st.warning(aviso)

    comparativo = ap.comparativo_avulsa(d, inst, base, acrescimo=forma.acrescimo)
    _resumo(ap.resumo_topo(d, comparativo, cotacao))

    st.markdown("#### Quanto você vai pagar")
    cols = st.columns(3)
    for col, (rot, usd, brl) in zip(cols, ap.totais(d, cotacao)):
        col.metric(rot, usd)
        col.caption(brl)
    st.markdown(f"**Cota da Receita:** {ap.situacao_cota(d)}.")
    st.markdown(ap.texto_pagamento(forma.nome, forma.acrescimo, d["resumo"]["custo_total"],
                                   r["d"]["resumo"]["custo_total"], cotacao))

    st.markdown("#### Onde comprar")
    if forma.acrescimo:
        st.caption(f"Preços já com o acréscimo de {forma.rotulo.split('(+')[1].rstrip(')')} "
                   f"por pagar com {forma.nome}.")
    itens = ap.tabela_itens(d, base, cotacao)
    if itens.empty:
        st.warning("Nenhum produto pôde ser comprado com estes dados.")
    else:
        st.dataframe(itens, hide_index=True, width="stretch")

    st.markdown("#### Seu roteiro")
    st.caption(f"Sai da Ponte da Amizade e volta para ela. Tempo andando: cerca de "
               f"{d['resumo']['tempo_andando']:.0f} min. Os horários já contam a caminhada, a espera "
               "até a loja abrir e o tempo de compra em cada loja.")
    if d["roteiro"]:
        _mapa(ap.dados_mapa(d, inst, base))
    st.dataframe(ap.tabela_roteiro(d), hide_index=True, width="stretch")

    _comparativo(comparativo, cotacao)

    fora = ap.tabela_fora(d, inst, orcamento_limita=False)
    if not fora.empty:
        st.markdown("#### Produtos que ficaram de fora")
        st.dataframe(fora, hide_index=True, width="stretch")

    f = _receita_federal(d, inst, cotacao)

    if consulta is not None:
        with st.expander("Todos os preços encontrados (produto × loja, em US$)"):
            st.dataframe(_matriz(consulta["res"]), width="stretch")
    avisos = list(d["avisos"]) + list(f["avisos"])
    if avisos:
        with st.expander(f"Avisos ({len(avisos)})"):
            for a in avisos:
                st.markdown(f"- {a}")


_localizacao = None


def _botao_localizacao():
    """Monta o botão de localização (registrado uma vez por sessão do servidor)."""
    global _localizacao
    if _localizacao is None:
        _localizacao = st.components.v2.component(
            "lesteshop_localizacao", html="<button>📍 Usar minha localização</button><span></span>",
            css=_CSS_LOCALIZACAO, js=_JS_LOCALIZACAO)
    return _localizacao(key="localizacao", on_posicao_change=lambda: None)


def _posicao_atual() -> dict | None:
    """Posição do aparelho: {"lat", "lon", "precisao"} ou {"erro"}; None se não pedida."""
    res = _botao_localizacao()
    pos = getattr(res, "posicao", None)
    return pos or st.session_state.get("posicao_teste")  # posicao_teste: só nos testes


def _passeio(r: dict, cotacao, forma) -> None:
    """4. Recalcular a rota durante o passeio (só com a localização ativa e dentro de
    Ciudad del Este)."""
    d0, inst0, base = r["d"], r["inst"], r["base"]
    if not d0["roteiro"]:
        return
    st.subheader("4. Já está no passeio? Recalcule a rota")
    st.caption("Se você se atrasou, mudou de caminho ou já passou em algumas lojas, o app refaz a rota "
               "com o que falta comprar, saindo de onde você está agora e voltando à Ponte. Para isso, "
               "a **localização do aparelho precisa estar ativa** e você precisa estar em "
               "**Ciudad del Este**.")
    nomes = {p["loja_id"]: f"{p['ordem']}. {p['nome']}" for p in d0["roteiro"]}
    feitas = st.multiselect("Lojas em que você já comprou", list(nomes), format_func=nomes.get,
                            key="passeio_feitas", placeholder="Nenhuma ainda")
    pos = _posicao_atual()
    if not pos:
        st.info("Clique em **Usar minha localização** e permita o acesso quando o navegador perguntar.")
        return
    if pos.get("erro"):
        st.warning(f"{pos['erro']} Ative a localização do aparelho e do navegador para recalcular a rota.")
        return
    lat, lon = float(pos["lat"]), float(pos["lon"])
    if not ps.em_ciudad_del_este(lat, lon):
        st.warning("Você não está em Ciudad del Este, então a rota não pode ser recalculada. "
                   "O recálculo só funciona durante o passeio, do lado paraguaio da Ponte.")
        return
    agora = ps.agora_no_paraguai()
    agora_min = agora.hour * 60 + agora.minute
    precisao = pos.get("precisao")
    texto_prec = f" (precisão de cerca de {precisao:.0f} m)" if isinstance(precisao, (int, float)) else ""
    st.success(f"Localização ativa em Ciudad del Este{texto_prec}. Agora são "
               f"{agora:%H:%M} no Paraguai.")
    if agora_min >= inst0.saida:
        st.warning(f"Já passou do horário em que você queria voltar à Ponte ({d0['horario_saida']}). "
                   "Mude o horário de volta na barra lateral e calcule de novo.")
        return
    if len(feitas) == len(d0["roteiro"]):
        st.info("Você já passou em todas as lojas do roteiro: é só voltar à Ponte da Amizade.")
        return
    if st.button("Recalcular a rota a partir daqui", type="primary"):
        inst_p, feito = ps.instancia_do_passeio(inst0, d0, set(feitas), lat, lon, agora_min)
        with st.spinner("Refazendo a rota com o que falta…"):
            sol, _ = resolver(inst_p, r=r.get("r", config_otim.R_PADRAO))
        st.session_state["passeio"] = {"sol": sol, "inst": inst_p, "feito": feito,
                                       "inicio": (lat, lon), "feitas": tuple(feitas)}
    p = st.session_state.get("passeio")
    if not p or p["feitas"] != tuple(feitas):
        return
    inst_nf = com_acrescimo(p["inst"], forma.acrescimo)
    d = descrever(p["sol"], inst_nf)
    st.markdown("#### Sua nova rota")
    if not d["roteiro"]:
        st.warning("Não dá mais tempo de passar em nenhuma loja antes do horário de volta.")
    else:
        _mapa(ap.dados_mapa(d, inst_nf, base, inicio=p["inicio"]), passeio=True)
        rot = ap.tabela_roteiro(d)
        rot.loc[0, ["Onde", "O que comprar"]] = ["Você está aqui", "agora"]
        st.dataframe(rot, hide_index=True, width="stretch")
    fora = ap.tabela_fora(d, p["inst"], orcamento_limita=False)
    if not fora.empty:
        st.markdown("**Produtos que não dá mais tempo de comprar**")
        st.dataframe(fora, hide_index=True, width="stretch")
    t = ps.totais_do_passeio(p["feito"], d, inst0, forma.acrescimo)
    c1, c2, c3 = st.columns(3)
    c1.metric("Já gastou", _valor(t["feito"], cotacao))
    c2.metric("Falta gastar", _valor(t["resto"], cotacao))
    c3.metric("Total da viagem, com imposto", _valor(t["custo_total"], cotacao))
    st.caption(f"Imposto da compra inteira: {ap.fmt_usd(t['imposto'])} "
               f"({'dentro da cota' if t['excedente'] <= 0 else 'passa da cota em ' + ap.fmt_usd(t['excedente'])}). "
               "A rota nova usa os mesmos preços do cálculo anterior e a mesma forma de pagamento.")


def main() -> None:
    st.set_page_config(page_title="LesteShop", page_icon="🛍️", layout="wide")
    if LOGO.exists():
        st.logo(str(LOGO), size="large")
    _estado()

    st.title("LesteShop")
    st.caption("Seu guia de compras em Ciudad del Este: onde comprar cada produto, o caminho "
               "saindo e voltando à Ponte da Amizade e quanto você paga de imposto na Receita.")

    modo, chegada, saida, orcamento, cotacao, forma, r_min = _barra_lateral()
    if modo == MODO_BASE and _base().origem != "real":
        st.warning(ap.texto_origem(_base())[1])
    pedidos = _lista_de_compras(_opcoes(modo))

    st.subheader("2. Calcular")
    assinatura = (modo, tuple(pedidos), chegada, saida, orcamento, r_min)
    if st.button("Calcular meu roteiro", type="primary", disabled=not pedidos):
        calcular = _calcular_consulta if modo == MODO_CONSULTA else _calcular_base
        r = calcular(pedidos, chegada, saida, orcamento, r_min)
        st.session_state["resultado"] = (None if r is None
                                         else {**r, "assinatura": assinatura, "orcamento": orcamento,
                                               "r": r_min})
        st.session_state["passeio"] = None

    r = st.session_state["resultado"]
    if r is not None:
        if r["assinatura"] != assinatura:
            st.info("A lista ou os dados da viagem mudaram: clique em **Calcular meu roteiro** de novo.")
        else:
            _resultado(r, r.get("cotacao") or cotacao, forma)
            _passeio(r, r.get("cotacao") or cotacao, forma)
