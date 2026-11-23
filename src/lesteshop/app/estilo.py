"""Visual do LesteShop (Fase 5, segunda versão do design, 23/11/2026).

CSS aplicado por cima do tema do Streamlit (``.streamlit/config.toml``): faixa de abertura
azul, etapas numeradas, cartões brancos com sombra sobre fundo azul bem claro, resumo com
números grandes e botão de cálculo em vermelho. Só aparência: nenhum cálculo passa por aqui.
"""

from __future__ import annotations

import streamlit as st

AZUL = "#0038A8"
AZUL_MEDIO = "#1F5BD8"
VERMELHO = "#D52B1E"
VERDE = "#0A8F4E"

CSS = f"""
<style>
/* Página */
.block-container {{ padding-top: 1.5rem; max-width: 1240px; }}
h1, h2, h3, h4 {{ letter-spacing: -0.01em; }}

/* Faixa de abertura */
.st-key-topo {{
  background: linear-gradient(115deg, {AZUL} 0%, {AZUL_MEDIO} 55%, #3C7DF2 100%);
  border-radius: 24px; padding: 1.6rem 2rem; position: relative; overflow: hidden;
  box-shadow: 0 10px 30px rgba(0, 56, 168, 0.25);
}}
.st-key-topo::after {{
  content: ""; position: absolute; right: -60px; top: -60px; width: 260px; height: 260px;
  border-radius: 50%; background: rgba(255, 255, 255, 0.08);
}}
.st-key-topo [data-testid="stImage"] img {{
  background: #fff; border-radius: 18px; padding: 10px 14px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.15);
}}
.ls-topo h1 {{ color: #fff; font-size: 2.1rem; line-height: 1.15; margin: 0 0 .4rem 0; padding: 0; }}
.ls-topo p {{ color: rgba(255,255,255,.9); font-size: 1.05rem; margin: 0 0 .9rem 0; }}
.ls-chips {{ display: flex; flex-wrap: wrap; gap: .5rem; }}
.ls-chips span {{
  background: rgba(255,255,255,.16); color: #fff; border: 1px solid rgba(255,255,255,.35);
  border-radius: 999px; padding: .3rem .8rem; font-size: .9rem; font-weight: 600;
}}
.ls-chips span b {{ color: #FFD7D3; }}

/* Etapas numeradas */
.ls-passo {{ display: flex; align-items: center; gap: .75rem; margin: .2rem 0 .6rem 0; }}
.ls-num {{
  flex: 0 0 auto; width: 2.3rem; height: 2.3rem; border-radius: 50%;
  background: {AZUL}; color: #fff; font-weight: 800; font-size: 1.15rem;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 10px rgba(0, 56, 168, .3);
}}
.ls-passo .ls-tit {{ font-size: 1.55rem; font-weight: 700; color: #14213D; }}
.ls-passo .ls-sub {{ display: block; font-size: .95rem; font-weight: 400; color: #5B6478; }}

/* Cartões */
[class*="st-key-cartao"] {{
  background: #fff; border-radius: 18px; padding: 1.3rem 1.5rem;
  box-shadow: 0 4px 20px rgba(20, 33, 61, .07); border: 1px solid #E3EAF6;
}}
[class*="st-key-cartao"] h4 {{ color: {AZUL}; padding-top: .1rem; }}

/* Resumo no topo do resultado */
.st-key-resumo [data-testid="stColumn"] {{
  background: #fff; border-radius: 16px; padding: 1rem 1.1rem;
  border: 1px solid #E3EAF6; border-top: 5px solid {AZUL};
  box-shadow: 0 4px 16px rgba(20, 33, 61, .07);
}}
.st-key-resumo [data-testid="stColumn"]:nth-child(2) {{ border-top-color: {VERDE}; }}
.st-key-resumo [data-testid="stColumn"]:nth-child(2) [data-testid="stMetricValue"] {{ color: {VERDE}; }}
.st-key-resumo [data-testid="stColumn"]:nth-child(4) {{ border-top-color: {VERMELHO}; }}
.st-key-resumo [data-testid="stMetricValue"] {{ color: {AZUL}; font-weight: 800; font-size: 1.8rem !important; }}
.st-key-resumo [data-testid="stMetricValue"] * {{
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
}}
[data-testid="stMetricValue"] {{ font-weight: 700; }}

/* Botões */
.stButton button[kind="primary"] {{ border-radius: 999px; font-weight: 700; }}
.st-key-calcular button {{
  background: linear-gradient(180deg, #E8392D, {VERMELHO}); border: none;
  font-size: 1.1rem; padding: .7rem 2.2rem; box-shadow: 0 6px 16px rgba(213, 43, 30, .35);
}}
.st-key-calcular button:hover {{ filter: brightness(1.05); }}
.st-key-calcular button:disabled {{ background: #D9DEE8; box-shadow: none; }}

/* Tabelas, caixas de aviso e barra lateral */
[data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; }}
[data-testid="stAlert"] {{ border-radius: 14px; }}
[data-testid="stSidebar"] {{ background: linear-gradient(180deg, #E7EEFB 0%, #F6F9FF 100%); }}
[data-testid="stSidebar"] h2 {{ color: {AZUL}; font-size: 1.15rem; }}
</style>
"""


def aplicar() -> None:
    st.html(CSS)


def topo(logo: str | None) -> None:
    """Faixa de abertura com o logotipo, a frase do app e os três passos."""
    with st.container(key="topo"):
        c1, c2 = st.columns([1, 2.2], vertical_alignment="center")
        if logo:
            c1.image(logo, width="stretch")
        c2.markdown(
            '<div class="ls-topo"><h1>Compre melhor em Ciudad del Este</h1>'
            "<p>Onde comprar cada produto, o caminho saindo e voltando à Ponte da Amizade "
            "e quanto você paga de imposto na Receita.</p>"
            '<div class="ls-chips"><span>🛒 Monte sua lista</span><span>🗺️ Siga o roteiro</span>'
            "<span>🧾 Saiba o imposto</span><span>💸 <b>Economize</b></span></div></div>",
            unsafe_allow_html=True)


def passo(numero: int | str, titulo: str, subtitulo: str | None = None) -> None:
    """Título de etapa com o número num círculo azul."""
    sub = f'<span class="ls-sub">{subtitulo}</span>' if subtitulo else ""
    st.markdown(f'<div class="ls-passo"><span class="ls-num">{numero}</span>'
                f'<span class="ls-tit">{titulo}{sub}</span></div>', unsafe_allow_html=True)


def cartao(chave: str):
    """Cartão branco com sombra (contêiner do Streamlit com classe própria)."""
    return st.container(key=f"cartao_{chave}")
