"""Avaliação de uma solução: gasto, imposto, prioridade, tempo e objetivo.

Objetivo (uma única resolução, aprovado com o professor):

    max  Σ v_k·y_k − λ·( G + α·E + r·Σ t_ij·x_ij ),   λ = 1 / (B + r·T_max + 1)

O imposto exibido é sempre recalculado depois de resolver:
α·max(0, G − c), por segurança contra tolerâncias numéricas do solver.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import config
from .instancia import Instancia, min_para_hhmm
from .rota import agenda


@dataclass
class Solucao:
    compras: dict[int, int]            # item k -> nó da loja i
    rota: list[int]                    # ordem de visita (sem o nó 0)
    r: float
    origem: str = ""                   # "exato", "heuristica"
    info: dict = field(default_factory=dict)

    def copia(self) -> "Solucao":
        return Solucao(dict(self.compras), list(self.rota), self.r, self.origem, dict(self.info))


@dataclass
class Avaliacao:
    viavel: bool
    motivo: str
    prioridade_total: int
    itens_comprados: int
    gasto_produtos: float     # G
    excedente: float          # max(0, G − c)
    imposto: float            # α·max(0, G − c)
    custo_total: float        # G + imposto
    tempo_andando: float      # Σ t_ij x_ij
    retorno: float
    peso_kg: float
    volume_l: float
    lambda_: float
    objetivo: float           # Σv − λ(G + αE + r·tempo)


def avaliar(sol: Solucao, inst: Instancia) -> Avaliacao:
    motivo = ""
    lojas_rota = set(sol.rota)
    for k, i in sol.compras.items():
        if (i, k) not in inst.preco:
            motivo = motivo or f"loja {i} não vende o item {k}"
        if i not in lojas_rota:
            motivo = motivo or f"loja {i} não está na rota"
    if len(lojas_rota) != len(sol.rota):
        motivo = motivo or "loja repetida na rota"
    G = sum(inst.custo_item(i, k) for k, i in sol.compras.items() if (i, k) in inst.preco)
    E = max(0.0, G - inst.cota)
    imposto = inst.aliquota * E
    if G + imposto > inst.orcamento + config.TOL:
        motivo = motivo or "orçamento excedido"
    peso = sum((inst.itens[k].peso_kg or 0.0) * inst.itens[k].quantidade for k in sol.compras)
    volume = sum((inst.itens[k].volume_l or 0.0) * inst.itens[k].quantidade for k in sol.compras)
    if inst.peso_max_kg is not None and peso > inst.peso_max_kg + config.TOL:
        motivo = motivo or "peso da bagagem excedido"
    if inst.volume_max_l is not None and volume > inst.volume_max_l + config.TOL:
        motivo = motivo or "volume da bagagem excedido"
    ag = agenda(sol.rota, inst)
    if not ag.viavel:
        motivo = motivo or ag.motivo
    prioridade = sum(inst.itens[k].prioridade for k in sol.compras)
    lam = inst.lambda_(sol.r)
    objetivo = prioridade - lam * (G + imposto + sol.r * ag.tempo_andando)
    return Avaliacao(
        viavel=not motivo, motivo=motivo, prioridade_total=prioridade,
        itens_comprados=len(sol.compras), gasto_produtos=round(G, 2), excedente=round(E, 2),
        imposto=round(imposto, 2), custo_total=round(G + imposto, 2),
        tempo_andando=ag.tempo_andando, retorno=ag.retorno, peso_kg=peso, volume_l=volume,
        lambda_=lam, objetivo=objetivo,
    )


def descrever(sol: Solucao, inst: Instancia) -> dict:
    """Dicionário legível (JSON) com itens, roteiro, gasto e situação da cota."""
    av = avaliar(sol, inst)
    ag = agenda(sol.rota, inst)
    roteiro = []
    for pos, i in enumerate(sol.rota):
        loja = inst.loja(i)
        compras = [
            {"produto_id": inst.itens[k].produto_id, "nome": inst.itens[k].nome,
             "quantidade": inst.itens[k].quantidade, "preco_usd": inst.preco[(i, k)]}
            for k, li in sorted(sol.compras.items()) if li == i
        ]
        roteiro.append({
            "ordem": pos + 1, "loja_id": loja.loja_id, "nome": loja.nome, "predio": loja.predio,
            "chegada": min_para_hhmm(ag.chegada[pos]), "inicio_atendimento": min_para_hhmm(ag.inicio[pos]),
            "saida": min_para_hhmm(ag.inicio[pos] + loja.permanencia), "compras": compras,
        })
    nao_comprados = [
        {"produto_id": it.produto_id, "nome": it.nome, "prioridade": it.prioridade}
        for k, it in enumerate(inst.itens) if k not in sol.compras
    ]
    return {
        "instancia": inst.nome, "origem": sol.origem, "r_usd_por_min": sol.r,
        "resumo": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(av).items()},
        "situacao_cota": (
            "dentro da cota" if av.excedente <= 0
            else f"excede a cota em US$ {av.excedente:.2f} (imposto US$ {av.imposto:.2f})"
        ),
        "cota_disponivel_usd": inst.cota, "orcamento_usd": inst.orcamento,
        "orcamento_informado": inst.orcamento_informado,
        "horario_chegada": min_para_hhmm(inst.chegada), "horario_saida": min_para_hhmm(inst.saida),
        "horario_retorno": min_para_hhmm(av.retorno),
        "roteiro": roteiro, "nao_comprados": nao_comprados,
        "avisos": inst.avisos, "info": sol.info,
    }
