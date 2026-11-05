"""Agenda de uma rota com janelas de tempo, 2-opt e polimento da ordem de visita.

Uma rota é a lista ordenada dos nós de loja visitados (sem o nó 0, que é
implícito no início e no fim). O turista sai da Ponte em H⁰, pode esperar a loja
abrir, fica ``permanencia`` minutos em cada loja e precisa voltar até H¹.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pulp

from . import config
from .instancia import Instancia


@dataclass
class Agenda:
    viavel: bool
    chegada: list[float]      # chegada a cada loja da rota
    inicio: list[float]       # início do atendimento (≥ abre)
    retorno: float            # volta ao nó 0
    tempo_andando: float      # Σ t_ij dos arcos usados
    motivo: str = ""


def tempo_andando(rota: list[int], inst: Instancia) -> float:
    if not rota:
        return 0.0
    nos = [0, *rota, 0]
    return float(sum(inst.t[a, b] for a, b in zip(nos, nos[1:])))


def agenda(rota: list[int], inst: Instancia) -> Agenda:
    """Calcula os horários da rota e verifica a viabilidade (janelas + volta até H¹)."""
    relogio = inst.chegada
    anterior = 0
    chegadas, inicios = [], []
    motivo = ""
    for i in rota:
        loja = inst.loja(i)
        chegada = relogio + inst.t[anterior, i]
        inicio = max(chegada, loja.abre)
        if inicio + loja.permanencia > loja.fecha + config.TOL and not motivo:
            motivo = f"loja {loja.loja_id} fecha antes do fim do atendimento"
        chegadas.append(chegada)
        inicios.append(inicio)
        relogio = inicio + loja.permanencia
        anterior = i
    retorno = relogio + inst.t[anterior, 0] if rota else inst.chegada
    if retorno > inst.saida + config.TOL and not motivo:
        motivo = "volta à Ponte depois do horário de saída"
    return Agenda(not motivo, chegadas, inicios, retorno, tempo_andando(rota, inst), motivo)


def melhor_insercao(rota: list[int], i: int, inst: Instancia) -> list[int] | None:
    """Insere o nó ``i`` na posição viável que menos aumenta o tempo andando."""
    melhor, melhor_t = None, float("inf")
    for pos in range(len(rota) + 1):
        nova = rota[:pos] + [i] + rota[pos:]
        ag = agenda(nova, inst)
        if ag.viavel and ag.tempo_andando < melhor_t - config.TOL:
            melhor, melhor_t = nova, ag.tempo_andando
    return melhor


def dois_opt(rota: list[int], inst: Instancia) -> list[int]:
    """2-opt + realocação de um nó (or-opt), mantendo a viabilidade. Minimiza o tempo andando."""
    atual = list(rota)
    t_atual = tempo_andando(atual, inst)
    melhorou = True
    while melhorou:
        melhorou = False
        n = len(atual)
        candidatas = []
        for a in range(n - 1):
            for b in range(a + 1, n):
                candidatas.append(atual[:a] + atual[a:b + 1][::-1] + atual[b + 1:])
        for a in range(n):
            resto = atual[:a] + atual[a + 1:]
            for pos in range(n):
                if pos != a:
                    candidatas.append(resto[:pos] + [atual[a]] + resto[pos:])
        for nova in candidatas:
            t_nova = tempo_andando(nova, inst)
            if t_nova < t_atual - config.TOL and agenda(nova, inst).viavel:
                atual, t_atual, melhorou = nova, t_nova, True
                break
    return atual


def ordem_exata(
    rota: list[int], inst: Instancia, limite_s: float = config.LIMITE_TEMPO_POLIMENTO_S
) -> list[int] | None:
    """Melhor ordem de visita para um conjunto fixo de lojas (TSP com janelas, PuLP+CBC).

    Devolve ``None`` se o solver não provar uma rota viável.
    """
    if len(rota) <= 1:
        return list(rota)
    nos = [0, *rota]
    arcos = [(a, b) for a in nos for b in nos if a != b]
    M = inst.big_m()
    prob = pulp.LpProblem("ordem_visita", pulp.LpMinimize)
    x = {(a, b): pulp.LpVariable(f"x_{a}_{b}", cat="Binary") for a, b in arcos}
    tau = {i: pulp.LpVariable(f"tau_{i}", inst.loja(i).abre, inst.loja(i).fecha - inst.loja(i).permanencia)
           for i in rota}
    R = pulp.LpVariable("R", inst.chegada, inst.saida)
    prob += pulp.lpSum(inst.t[a, b] * x[a, b] for a, b in arcos)
    for v in nos:
        prob += pulp.lpSum(x[v, b] for b in nos if b != v) == 1
        prob += pulp.lpSum(x[a, v] for a in nos if a != v) == 1
    for i in rota:
        s_i = inst.loja(i).permanencia
        prob += tau[i] >= inst.chegada + inst.t[0, i] - M * (1 - x[0, i])
        prob += R >= tau[i] + s_i + inst.t[i, 0] - M * (1 - x[i, 0])
        for j in rota:
            if i != j:
                prob += tau[j] >= tau[i] + s_i + inst.t[i, j] - M * (1 - x[i, j])
    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=limite_s))
    if pulp.LpStatus[prob.status] != "Optimal":
        return None
    seq, atual = [], 0
    for _ in range(len(rota)):
        atual = next(b for b in nos if b != atual and (x[atual, b].value() or 0) > 0.5)
        seq.append(atual)
    return seq if agenda(seq, inst).viavel else None


@dataclass
class Polimento:
    rota: list[int]
    metodo: str               # "exato", "2-opt" ou "nenhum"
    tempo_andando_antes: float
    tempo_andando_depois: float
    aceito: bool
    tempo_s: float


def polir_rota(rota: list[int], inst: Instancia) -> Polimento:
    """Mantém as lojas e reotimiza só a ORDEM de visita.

    Exato (PuLP) com até ``POLIMENTO_EXATO_MAX_LOJAS`` lojas, senão 2-opt. A nova
    ordem só é aceita se for viável e reduzir o tempo andando (em empate, fica a original).
    """
    inicio = time.perf_counter()
    antes = tempo_andando(rota, inst)
    if len(rota) <= 2:  # com 1 ou 2 lojas a ordem não muda o tempo (matriz simétrica)
        return Polimento(list(rota), "nenhum", antes, antes, False, time.perf_counter() - inicio)
    if len(rota) <= config.POLIMENTO_EXATO_MAX_LOJAS:
        metodo, nova = "exato", ordem_exata(rota, inst)
        if nova is None:
            metodo, nova = "2-opt", dois_opt(rota, inst)
    else:
        metodo, nova = "2-opt", dois_opt(rota, inst)
    depois = tempo_andando(nova, inst)
    # Regra aprovada: só aceita se for viável e não aumentar o tempo andando. Empates
    # (ex.: a mesma rota invertida) mantêm a ordem original, para não trocar à toa.
    aceito = agenda(nova, inst).viavel and depois < antes - config.TOL
    if not aceito:
        nova, depois = list(rota), antes
    return Polimento(nova, metodo, antes, depois, aceito, time.perf_counter() - inicio)
