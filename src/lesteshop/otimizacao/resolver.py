"""Resolve uma instância e mostra itens, lojas, roteiro, gasto e situação da cota.

Exemplos::

    python -m lesteshop.otimizacao.resolver data/instances/inst_001_pequena
    python -m lesteshop.otimizacao.resolver data/instances/inst_081_grande --r 1 --json saida.json
    python -m lesteshop.otimizacao.resolver data/instances/inst_002_pequena --sem-orcamento
    python -m lesteshop.otimizacao.resolver data/instances/inst_010_pequena --peso-max 10
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import config
from .heuristica import resolver_heuristica
from .instancia import Instancia, carregar_instancia, min_para_hhmm
from .modelo import resolver_exato
from .rota import polir_rota
from .solucao import Solucao, avaliar, descrever


def resolver(
    inst: Instancia,
    r: float = config.R_PADRAO,
    limite_s: float | None = None,
    so_heuristica: bool = False,
) -> tuple[Solucao, Solucao]:
    """Heurística (polida) → modelo exato com warm start → polimento da rota.

    Devolve (solução final, solução da heurística). Os dados de status, gap,
    tempos e polimento ficam em ``Solucao.info``.
    """
    heur = resolver_heuristica(inst, r)
    pol_h = polir_rota(heur.rota, inst)
    heur.rota = pol_h.rota
    heur.info.update(tempo_andando_antes_polimento=pol_h.tempo_andando_antes,
                     tempo_andando_depois_polimento=pol_h.tempo_andando_depois,
                     polimento=pol_h.metodo, polimento_aceito=pol_h.aceito)
    if so_heuristica:
        return heur, heur
    res = resolver_exato(inst, r, limite_s, solucao_inicial=heur)
    final = res.solucao
    pol = polir_rota(final.rota, inst)
    final.rota = pol.rota
    final.info.update(
        status=res.status, gap=res.gap, tempo_s=res.tempo_s, big_m=res.big_m,
        objetivo_modelo=res.objetivo_modelo, limitante=res.limitante,
        n_variaveis=res.n_variaveis, n_restricoes=res.n_restricoes,
        tempo_andando_antes_polimento=pol.tempo_andando_antes,
        tempo_andando_depois_polimento=pol.tempo_andando_depois,
        polimento=pol.metodo, polimento_aceito=pol.aceito, tempo_polimento_s=pol.tempo_s,
    )
    # Segurança: nunca devolver solução pior que a da heurística.
    if avaliar(heur, inst).objetivo > avaliar(final, inst).objetivo + config.TOL:
        info = final.info
        final = heur.copia()
        final.origem = "heuristica (melhor que o exato no limite de tempo)"
        final.info = {**info, **{k: v for k, v in heur.info.items() if "polimento" in k}}
    return final, heur


def imprimir(sol: Solucao, inst: Instancia) -> None:
    d = descrever(sol, inst)
    av = d["resumo"]
    print(f"Instância {inst.nome} — {inst.m} lojas candidatas, {len(inst.itens)} itens na lista")
    if inst.lojas_excluidas or inst.avisos:
        for a in inst.avisos:
            print(f"  aviso: {a}")
    info = sol.info
    if "status" in info:
        gap = "—" if info["gap"] is None else f"{100 * info['gap']:.3f}%"
        print(f"Solver: {info['status']}, gap {gap}, {info['tempo_s']:.2f} s, M = {info['big_m']:.1f} min")
    print(f"r = US$ {sol.r:.2f}/min, λ = {av['lambda_']:.6f}")
    print()
    print(f"Saída da Ponte da Amizade às {d['horario_chegada']}")
    for parada in d["roteiro"]:
        print(f"  {parada['ordem']}. {parada['nome']} ({parada['predio'] or 'sem prédio'}) "
              f"— chega {parada['chegada']}, atende {parada['inicio_atendimento']}–{parada['saida']}")
        for c in parada["compras"]:
            print(f"       {c['quantidade']}× {c['nome']}: US$ {c['preco_usd']:.2f}")
    print(f"Volta à Ponte às {d['horario_retorno']} (limite {d['horario_saida']})")
    if d["nao_comprados"]:
        print("Itens deixados de fora:")
        for it in d["nao_comprados"]:
            print(f"  - {it['nome']} (prioridade {it['prioridade']})")
    print()
    print(f"Prioridade atendida: {av['prioridade_total']} de {sum(it.prioridade for it in inst.itens)}")
    print(f"Gasto em produtos: US$ {av['gasto_produtos']:.2f}")
    print(f"Imposto (50% sobre o excedente da cota de US$ {inst.cota:.2f}): US$ {av['imposto']:.2f}")
    print(f"Custo total: US$ {av['custo_total']:.2f} "
          f"(orçamento US$ {inst.orcamento:.2f}{'' if inst.orcamento_informado else ', = cota'})")
    print(f"Situação da cota: {d['situacao_cota']}")
    print(f"Tempo andando: {av['tempo_andando']:.1f} min", end="")
    if "tempo_andando_antes_polimento" in info:
        print(f" (antes do polimento: {info['tempo_andando_antes_polimento']:.1f} min)", end="")
    print()
    print(f"Bagagem: {av['peso_kg']:.2f} kg, {av['volume_l']:.1f} L")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Resolve uma instância do LesteShop (Fase 2).")
    p.add_argument("pasta", type=Path, help="pasta da instância (data/instances/inst_...)")
    p.add_argument("--r", type=float, default=config.R_PADRAO, help="valor do minuto andando (US$)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--orcamento", type=float, help="substitui o orçamento do metadata.json")
    g.add_argument("--sem-orcamento", action="store_true", help="turista sem orçamento (teto = cota)")
    p.add_argument("--peso-max", type=float, help="limite de peso da bagagem (kg)")
    p.add_argument("--volume-max", type=float, help="limite de volume da bagagem (L)")
    p.add_argument("--limite-tempo", type=float, help="limite do solver em segundos")
    p.add_argument("--so-heuristica", action="store_true")
    p.add_argument("--json", type=Path, help="grava a solução completa em JSON")
    a = p.parse_args(argv)
    orc = None if a.sem_orcamento else (a.orcamento if a.orcamento is not None else "instancia")
    inst = carregar_instancia(a.pasta, orcamento=orc, peso_max_kg=a.peso_max, volume_max_l=a.volume_max)
    inicio = time.perf_counter()
    sol, _ = resolver(inst, a.r, a.limite_tempo, a.so_heuristica)
    imprimir(sol, inst)
    print(f"\nTempo total: {time.perf_counter() - inicio:.2f} s")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(descrever(sol, inst), ensure_ascii=False, indent=2, default=float),
                          encoding="utf-8")
        print(f"Solução gravada em {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
