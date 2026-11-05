"""Modelo exato da Fase 2 (PuLP + CBC).

TPP com mochila, cota de isenção, imposto sobre o excedente e janelas de tempo.
Formulação completa em docs/modelo_matematico.md. Para o solver, a função
objetivo é multiplicada pela constante K = 1/λ = B + r·T_max + 1 > 0, o que não
muda o ótimo e evita coeficientes muito pequenos:

    max  K·Σ v_k·y_k − ( G + α·E + r·Σ t_ij·x_ij )
"""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pulp

from . import config
from .instancia import Instancia
from .rota import agenda
from .solucao import Solucao, avaliar


@dataclass
class ResultadoExato:
    solucao: Solucao
    status: str          # "otimo", "viavel (limite de tempo)", "sem solucao"
    gap: float | None    # gap relativo (incumbente × limitante), na escala de K·objetivo
    tempo_s: float
    big_m: float
    objetivo_modelo: float | None  # objetivo original (Σv − λ·...) segundo o solver
    limitante: float | None        # limitante superior do objetivo original
    n_variaveis: int
    n_restricoes: int


def construir(inst: Instancia, r: float):
    """Monta o problema PuLP. Devolve (prob, variáveis)."""
    lojas = list(inst.nos_lojas)
    nos = [0, *lojas]
    K = 1.0 / inst.lambda_(r)
    M = inst.big_m()
    arcos = [(a, b) for a in nos for b in nos if a != b]
    pares = list(inst.preco)                     # (i, k) com oferta
    itens_com_oferta = sorted({k for _, k in pares})

    prob = pulp.LpProblem(f"TPP_{inst.nome}", pulp.LpMaximize)
    x = {(a, b): pulp.LpVariable(f"x_{a}_{b}", cat="Binary") for a, b in arcos}
    z = {i: pulp.LpVariable(f"z_{i}", cat="Binary") for i in lojas}
    u = {(i, k): pulp.LpVariable(f"u_{i}_{k}", cat="Binary") for i, k in pares}
    y = {k: pulp.LpVariable(f"y_{k}", cat="Binary") for k in itens_com_oferta}
    G = pulp.LpVariable("G", lowBound=0)
    E = pulp.LpVariable("E", lowBound=0)
    tau = {i: pulp.LpVariable(f"tau_{i}", inst.loja(i).abre, inst.loja(i).fecha - inst.loja(i).permanencia)
           for i in lojas}
    R = pulp.LpVariable("R", inst.chegada, inst.saida)
    andando = pulp.lpSum(inst.t[a, b] * x[a, b] for a, b in arcos)

    # Função objetivo (× K)
    prob += K * pulp.lpSum(inst.itens[k].prioridade * y[k] for k in y) - (G + inst.aliquota * E + r * andando)

    # (1) atribuição: cada item comprado em exatamente uma loja
    for k in y:
        prob += pulp.lpSum(u[i, k] for i in inst.lojas_do_item(k)) == y[k], f"atrib_{k}"
    # (2) compra só em loja visitada; loja visitada só se comprar algo
    for (i, k), var in u.items():
        prob += var <= z[i], f"visita_{i}_{k}"
    for i in lojas:
        prob += z[i] <= pulp.lpSum(u[i, k] for k in inst.itens_da_loja(i)), f"util_{i}"
    # (3) grau
    for i in lojas:
        prob += pulp.lpSum(x[i, b] for b in nos if b != i) == z[i], f"sai_{i}"
        prob += pulp.lpSum(x[a, i] for a in nos if a != i) == z[i], f"entra_{i}"
        prob += z[i] <= pulp.lpSum(x[0, b] for b in lojas), f"usa_ponte_{i}"
    prob += pulp.lpSum(x[0, b] for b in lojas) == pulp.lpSum(x[a, 0] for a in lojas), "ponte_grau"
    prob += pulp.lpSum(x[0, b] for b in lojas) <= 1, "ponte_uma_saida"
    # (4) gasto, (5) excedente, (6) orçamento
    prob += G == pulp.lpSum(inst.custo_item(i, k) * u[i, k] for i, k in pares), "gasto"
    prob += E >= G - inst.cota, "excedente"
    prob += G + inst.aliquota * E <= inst.orcamento, "orcamento"
    # (7) janelas de tempo (também eliminam subrotas)
    for j in lojas:
        prob += tau[j] >= inst.chegada + inst.t[0, j] - M * (1 - x[0, j]), f"tw_ponte_{j}"
        prob += R >= tau[j] + inst.loja(j).permanencia + inst.t[j, 0] - M * (1 - x[j, 0]), f"tw_volta_{j}"
        for i in lojas:
            if i != j:
                prob += (tau[j] >= tau[i] + inst.loja(i).permanencia + inst.t[i, j] - M * (1 - x[i, j]),
                         f"tw_{i}_{j}")
    # (8) bagagem (opcional)
    if inst.peso_max_kg is not None:
        prob += pulp.lpSum((inst.itens[k].peso_kg or 0) * inst.itens[k].quantidade * y[k] for k in y) \
            <= inst.peso_max_kg, "peso"
    if inst.volume_max_l is not None:
        prob += pulp.lpSum((inst.itens[k].volume_l or 0) * inst.itens[k].quantidade * y[k] for k in y) \
            <= inst.volume_max_l, "volume"
    return prob, {"x": x, "z": z, "u": u, "y": y, "G": G, "E": E, "tau": tau, "R": R, "K": K, "M": M}


def _iniciar_com(var: dict, sol: Solucao, inst: Instancia) -> None:
    """Valores iniciais (warm start) a partir de uma solução viável."""
    ag = agenda(sol.rota, inst)
    arcos_usados = set()
    if sol.rota:
        nos = [0, *sol.rota, 0]
        arcos_usados = set(zip(nos, nos[1:]))
    for a_b, v in var["x"].items():
        v.setInitialValue(1 if a_b in arcos_usados else 0)
    for i, v in var["z"].items():
        v.setInitialValue(1 if i in sol.rota else 0)
    for (i, k), v in var["u"].items():
        v.setInitialValue(1 if sol.compras.get(k) == i else 0)
    for k, v in var["y"].items():
        v.setInitialValue(1 if k in sol.compras else 0)
    G = sum(inst.custo_item(i, k) for k, i in sol.compras.items())
    var["G"].setInitialValue(G)
    var["E"].setInitialValue(max(0.0, G - inst.cota))
    inicio = dict(zip(sol.rota, ag.inicio))
    for i, v in var["tau"].items():
        v.setInitialValue(inicio.get(i, inst.loja(i).abre))
    var["R"].setInitialValue(ag.retorno)


def _ler_log_cbc(texto: str) -> tuple[bool, float | None]:
    """(ótimo provado?, |limitante| na escala K·objetivo) a partir do log do CBC.

    O CBC resolve internamente a minimização de −(objetivo), então o "best
    possible" vem com o sinal trocado; como a solução vazia é sempre viável e tem
    objetivo 0, o limitante superior é ≥ 0 e basta o valor absoluto.
    """
    otimo = "Result - Optimal solution found" in texto
    achados = re.findall(r"best possible (-?[\d.eE+-]+)\)", texto)
    if achados:
        return otimo, abs(float(achados[-1]))
    m = re.search(r"(?:Lower|Upper) bound:\s+(-?[\d.eE+-]+)", texto)
    return otimo, abs(float(m.group(1))) if m else None


def _extrair(var: dict, inst: Instancia, r: float) -> Solucao:
    compras = {k: i for (i, k), v in var["u"].items() if (v.value() or 0) > 0.5}
    seq, atual = [], 0
    visitadas = {i for i, v in var["z"].items() if (v.value() or 0) > 0.5}
    for _ in range(len(visitadas)):
        prox = [b for (a, b), v in var["x"].items() if a == atual and b != 0 and (v.value() or 0) > 0.5]
        if not prox:
            break
        atual = prox[0]
        seq.append(atual)
    return Solucao(compras, seq, r, "exato")


def resolver_exato(
    inst: Instancia,
    r: float = config.R_PADRAO,
    limite_s: float | None = None,
    solucao_inicial: Solucao | None = None,
    msg: bool = False,
) -> ResultadoExato:
    if limite_s is None:
        limite_s = config.LIMITE_TEMPO_S.get(inst.tamanho or "", config.LIMITE_TEMPO_PADRAO_S)
    prob, var = construir(inst, r)
    K = var["K"]
    warm = solucao_inicial is not None and avaliar(solucao_inicial, inst).viavel
    if warm:
        _iniciar_com(var, solucao_inicial, inst)
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "cbc.log"
        solver = pulp.PULP_CBC_CMD(msg=msg, timeLimit=limite_s, warmStart=warm, logPath=str(log),
                                   threads=1)
        inicio = time.perf_counter()
        prob.solve(solver)
        tempo = time.perf_counter() - inicio
        texto_log = log.read_text(errors="ignore") if log.exists() else ""

    tem_solucao = prob.sol_status in (pulp.LpSolutionOptimal, pulp.LpSolutionIntegerFeasible)
    if not tem_solucao:
        # Sem incumbente: devolve a solução vazia (sempre viável) ou a inicial.
        sol = solucao_inicial.copia() if warm else Solucao({}, [], r)
        sol.origem = "exato"
        return ResultadoExato(sol, "sem solucao", None, tempo, var["M"], None, None,
                              len(prob.variables()), len(prob.constraints))

    sol = _extrair(var, inst, r)
    obj_k = pulp.value(prob.objective)
    otimo, lim_cbc = _ler_log_cbc(texto_log)
    otimo = otimo or (prob.sol_status == pulp.LpSolutionOptimal and "Stopped on time" not in texto_log)
    if otimo:
        limitante_k, gap = obj_k, 0.0
    elif lim_cbc is not None:
        limitante_k = max(lim_cbc, obj_k)
        gap = (limitante_k - obj_k) / max(abs(obj_k), 1e-9)
    else:
        limitante_k, gap = None, None
    status = "otimo" if otimo else "viavel (limite de tempo)"
    return ResultadoExato(
        solucao=sol, status=status, gap=gap, tempo_s=tempo, big_m=var["M"],
        objetivo_modelo=obj_k / K, limitante=None if limitante_k is None else limitante_k / K,
        n_variaveis=len(prob.variables()), n_restricoes=len(prob.constraints),
    )
