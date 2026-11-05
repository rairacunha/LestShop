"""Heurística para o TPP com mochila, cota, imposto e janelas de tempo.

Usada como solução inicial (warm start) do modelo exato e como comparação nos
experimentos. Mesma função objetivo do modelo exato (ver ``solucao.avaliar``).

1. **Construção gulosa**, repetida para três ordens dos itens (prioridade e
   menor preço; prioridade ÷ menor preço; menor preço). Para cada item, testa
   todas as lojas que o vendem: compra em loja já visitada ou insere a loja na
   melhor posição viável da rota; fica com a opção de maior objetivo que
   respeite orçamento, bagagem e janelas. Se nenhuma couber, o item fica de fora.
2. **Busca local** (primeira melhora, até não haver melhora):
   * trocar a loja de um item comprado;
   * incluir um item que ficou de fora;
   * trocar um item comprado por um que ficou de fora (e reencher a mochila);
   * 2-opt / realocação na ordem da rota.
3. Lojas que ficam sem compras saem da rota.
"""

from __future__ import annotations

import time

from . import config
from .instancia import Instancia
from .rota import dois_opt, melhor_insercao
from .solucao import Solucao, avaliar


def _objetivo(sol: Solucao, inst: Instancia) -> float | None:
    av = avaliar(sol, inst)
    return av.objetivo if av.viavel else None


def _limpar(sol: Solucao) -> Solucao:
    usadas = set(sol.compras.values())
    sol.rota = [i for i in sol.rota if i in usadas]
    return sol


def _com_compra(sol: Solucao, k: int, i: int, inst: Instancia) -> Solucao | None:
    """Cópia de ``sol`` comprando o item k na loja i (inserindo a loja se preciso)."""
    nova = sol.copia()
    nova.compras[k] = i
    _limpar(nova)
    if i not in nova.rota:
        rota = melhor_insercao(nova.rota, i, inst)
        if rota is None:
            return None
        nova.rota = rota
    return nova


def _melhor_opcao(sol: Solucao, k: int, inst: Instancia) -> tuple[Solucao, float] | None:
    melhor = None
    for i in inst.lojas_do_item(k):
        cand = _com_compra(sol, k, i, inst)
        if cand is None:
            continue
        obj = _objetivo(cand, inst)
        if obj is not None and (melhor is None or obj > melhor[1] + config.TOL):
            melhor = (cand, obj)
    return melhor


def _encher(sol: Solucao, inst: Instancia, ordem: list[int]) -> Solucao:
    for k in ordem:
        if k in sol.compras:
            continue
        op = _melhor_opcao(sol, k, inst)
        if op is not None:
            sol = op[0]
    return sol


def _ordens(inst: Instancia) -> list[list[int]]:
    ks = [k for k in range(len(inst.itens)) if inst.lojas_do_item(k)]
    menor = {k: min(inst.custo_item(i, k) for i in inst.lojas_do_item(k)) for k in ks}
    v = {k: inst.itens[k].prioridade for k in ks}
    return [
        sorted(ks, key=lambda k: (-v[k], menor[k])),
        sorted(ks, key=lambda k: (-v[k] / menor[k], menor[k])),
        sorted(ks, key=lambda k: (menor[k], -v[k])),
    ]


def _busca_local(sol: Solucao, inst: Instancia, ordem: list[int], limite_s: float, inicio: float) -> Solucao:
    obj = _objetivo(sol, inst)
    melhorou = True
    while melhorou and time.perf_counter() - inicio < limite_s:
        melhorou = False
        # (a) trocar a loja de um item comprado
        for k, i_atual in list(sol.compras.items()):
            for i in inst.lojas_do_item(k):
                if i == i_atual:
                    continue
                cand = _com_compra(sol, k, i, inst)
                o = _objetivo(cand, inst) if cand else None
                if o is not None and o > obj + config.TOL:
                    sol, obj, melhorou = cand, o, True
                    break
            if melhorou:
                break
        if melhorou:
            continue
        # (b) incluir item que ficou de fora
        for k in ordem:
            if k in sol.compras:
                continue
            op = _melhor_opcao(sol, k, inst)
            if op is not None and op[1] > obj + config.TOL:
                sol, obj, melhorou = op[0], op[1], True
                break
        if melhorou:
            continue
        # (c) trocar um item comprado por um de fora e reencher
        for k_sai in list(sol.compras):
            base = sol.copia()
            del base.compras[k_sai]
            _limpar(base)
            for k_entra in ordem:
                if k_entra in sol.compras:
                    continue
                op = _melhor_opcao(base, k_entra, inst)
                if op is None:
                    continue
                cand = _encher(op[0], inst, [k for k in ordem if k != k_sai])
                o = _objetivo(cand, inst)
                if o is not None and o > obj + config.TOL:
                    sol, obj, melhorou = cand, o, True
                    break
            if melhorou:
                break
        if melhorou:
            continue
        # (d) ordem da rota
        cand = sol.copia()
        cand.rota = dois_opt(sol.rota, inst)
        o = _objetivo(cand, inst)
        if o is not None and o > obj + config.TOL:
            sol, obj, melhorou = cand, o, True
    return sol


def resolver_heuristica(inst: Instancia, r: float = config.R_PADRAO, limite_s: float = 60.0) -> Solucao:
    inicio = time.perf_counter()
    melhor, melhor_obj = Solucao({}, [], r, "heuristica"), 0.0  # solução vazia é sempre viável
    for ordem in _ordens(inst):
        sol = _encher(Solucao({}, [], r, "heuristica"), inst, ordem)
        sol = _busca_local(sol, inst, ordem, limite_s, inicio)
        obj = _objetivo(sol, inst)
        if obj is not None and obj > melhor_obj + config.TOL:
            melhor, melhor_obj = sol, obj
    melhor.origem = "heuristica"
    melhor.info["tempo_s"] = time.perf_counter() - inicio
    return melhor
