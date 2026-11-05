"""Experimentos da Fase 2 sobre as 100 instâncias de data/instances (inst_001…inst_100).

* r = 0,25 em todas as instâncias;
* análise de sensibilidade: r = 0 e r = 1 nas pequenas e médias.

Para cada (instância, r): heurística (+ polimento) → modelo exato com warm start
(limite de 60 s nas pequenas/médias e 300 s nas grandes) → polimento da rota.

Saídas em data/resultados/:

* ``resultados_fase2.csv``: uma linha por (instância, r);
* ``solucoes/r<r>/<instancia>.json``: solução final detalhada;
* ``resumo_experimentos.md``: tabelas por tamanho, heurística × exato e efeito de r.

Uso::

    python -m lesteshop.otimizacao.experimentos                 # tudo
    python -m lesteshop.otimizacao.experimentos --processos 3   # em paralelo
    python -m lesteshop.otimizacao.experimentos --so-resumo     # refaz só o resumo
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from . import config
from ..data import config as config_dados
from .instancia import carregar_instancia
from .resolver import resolver
from .solucao import avaliar, descrever

R_SENSIBILIDADE = (0.0, 1.0)
TAMANHOS = ("pequena", "media", "grande")


def listar_instancias(pasta: Path = config_dados.DIR_INSTANCIAS) -> list[Path]:
    return sorted(p for p in pasta.glob("inst_*") if (p / "metadata.json").exists())


def rodadas(instancias: list[Path], r_base: float = config.R_PADRAO) -> list[tuple[Path, float]]:
    lista = [(p, r_base) for p in instancias]
    for r in R_SENSIBILIDADE:
        for p in instancias:
            tam = json.loads((p / "metadata.json").read_text(encoding="utf-8")).get("tamanho")
            if tam in ("pequena", "media"):
                lista.append((p, r))
    return lista


def _rotulo_r(r: float) -> str:
    return f"r{r:g}"


def executar(pasta: Path, r: float, dir_saida: Path) -> dict:
    inst = carregar_instancia(pasta)
    inicio = time.perf_counter()
    final, heur = resolver(inst, r)
    total = time.perf_counter() - inicio
    af, ah = avaliar(final, inst), avaliar(heur, inst)
    fi, hi = final.info, heur.info
    destino = dir_saida / "solucoes" / _rotulo_r(r) / f"{inst.nome}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(descrever(final, inst), ensure_ascii=False, indent=2, default=float),
                       encoding="utf-8")
    meta = inst.metadata
    return {
        "instancia": inst.nome, "tamanho": inst.tamanho, "r": r,
        "n_lojas": meta.get("n_lojas"), "n_lojas_modelo": inst.m, "n_itens": len(inst.itens),
        "n_lojas_excluidas": len(inst.lojas_excluidas),
        "cota": inst.cota, "orcamento": inst.orcamento,
        "custo_minimo_lista": meta.get("custo_minimo_lista_usd"),
        "lambda": af.lambda_, "big_m": fi.get("big_m"),
        "n_variaveis": fi.get("n_variaveis"), "n_restricoes": fi.get("n_restricoes"),
        "status": fi.get("status"), "gap": fi.get("gap"), "tempo_exato_s": fi.get("tempo_s"),
        "limite_s": config.LIMITE_TEMPO_S.get(inst.tamanho, config.LIMITE_TEMPO_PADRAO_S),
        "origem_final": final.origem,
        "objetivo": af.objetivo, "limitante": fi.get("limitante"),
        "prioridade": af.prioridade_total, "prioridade_lista": sum(it.prioridade for it in inst.itens),
        "itens_comprados": af.itens_comprados,
        "gasto_produtos": af.gasto_produtos, "imposto": af.imposto, "custo_total": af.custo_total,
        "tempo_andando": af.tempo_andando,
        "tempo_andando_antes_polimento": fi.get("tempo_andando_antes_polimento"),
        "polimento": fi.get("polimento"), "polimento_aceito": fi.get("polimento_aceito"),
        "lojas_visitadas": len(final.rota), "retorno_min": af.retorno,
        "peso_kg": af.peso_kg, "volume_l": af.volume_l,
        "heur_objetivo": ah.objetivo, "heur_prioridade": ah.prioridade_total,
        "heur_custo_total": ah.custo_total, "heur_tempo_andando": ah.tempo_andando,
        "heur_tempo_andando_antes_polimento": hi.get("tempo_andando_antes_polimento"),
        "heur_polimento_aceito": hi.get("polimento_aceito"),
        "heur_lojas_visitadas": len(heur.rota), "heur_tempo_s": hi.get("tempo_s"),
        "tempo_total_s": total, "viavel": af.viavel and ah.viavel,
    }


def _aquecer() -> None:
    """Resolve um problema trivial para carregar o CBC antes de medir tempos.

    Sem isso, a primeira chamada de cada processo inclui a carga do executável
    (até ~10 s observados), o que distorce o tempo de uma instância pequena.
    """
    import pulp

    p = pulp.LpProblem("aquecimento", pulp.LpMaximize)
    v = pulp.LpVariable("v", 0, 1, cat="Binary")
    p += v
    p.solve(pulp.PULP_CBC_CMD(msg=False))


def _tarefa(args):
    pasta, r, dir_saida = args
    linha = executar(Path(pasta), r, Path(dir_saida))
    print(f"{linha['instancia']} r={r:g}: {linha['status']}, {linha['tempo_exato_s']:.2f} s", flush=True)
    return linha


def rodar(processos: int = 1, dir_saida: Path = config.DIR_RESULTADOS,
          instancias: list[Path] | None = None) -> pd.DataFrame:
    instancias = instancias or listar_instancias()
    tarefas = [(str(p), r, str(dir_saida)) for p, r in rodadas(instancias)]
    # As grandes primeiro, para equilibrar a carga entre os processos.
    tarefas.sort(key=lambda t: "grande" not in t[0])
    if processos > 1:
        with ProcessPoolExecutor(processos, initializer=_aquecer) as ex:
            linhas = list(ex.map(_tarefa, tarefas))
    else:
        _aquecer()
        linhas = [_tarefa(t) for t in tarefas]
    df = pd.DataFrame(linhas).sort_values(["r", "instancia"]).reset_index(drop=True)
    dir_saida.mkdir(parents=True, exist_ok=True)
    df.to_csv(dir_saida / "resultados_fase2.csv", index=False)
    return df


# --- Resumo -----------------------------------------------------------------

def _md(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    linhas = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        linhas.append("| " + " | ".join(str(v) for v in row.tolist()) + " |")
    return "\n".join(linhas)


def resumo(df: pd.DataFrame, processos: int | None = None) -> str:
    base = df[df["r"] == config.R_PADRAO].copy()
    partes = [
        "# Resultados dos experimentos — Fase 2",
        "",
        "Gerado por `python -m lesteshop.otimizacao.experimentos`. Base **fictícia** "
        "(`tipo_dado = sintetico`); os números servem para avaliar o modelo, não para decisões de compra.",
        "",
        f"Configuração: PuLP + CBC (1 thread por instância{f', {processos} instâncias em paralelo' if processos else ''}), "
        "limite de 60 s (pequenas e médias) e 300 s (grandes); heurística como solução inicial; "
        f"r = {config.R_PADRAO} US$/min, exceto na análise de sensibilidade.",
        "",
        "Tempos são de relógio (wall clock), com as instâncias rodando em paralelo; a mediana é "
        "menos sensível a atrasos pontuais do sistema operacional ao iniciar o CBC.",
        "",
        f"## 1. Modelo exato por tamanho (r = {config.R_PADRAO})",
        "",
    ]
    t1 = []
    for tam in TAMANHOS:
        d = base[base["tamanho"] == tam]
        if d.empty:
            continue
        t1.append({
            "tamanho": tam, "instâncias": len(d),
            "lojas no modelo (méd/máx)": f"{d['n_lojas_modelo'].mean():.1f} / {d['n_lojas_modelo'].max()}",
            "itens (méd/máx)": f"{d['n_itens'].mean():.1f} / {d['n_itens'].max()}",
            "variáveis (méd)": f"{d['n_variaveis'].mean():.0f}",
            "ótimo": int((d["status"] == "otimo").sum()),
            "limite de tempo": int((d["status"] != "otimo").sum()),
            "gap méd / máx (%)": f"{100 * d['gap'].fillna(0).mean():.3f} / {100 * d['gap'].fillna(0).max():.3f}",
            "tempo méd / mediana / máx (s)":
                f"{d['tempo_exato_s'].mean():.2f} / {d['tempo_exato_s'].median():.2f} / {d['tempo_exato_s'].max():.2f}",
            "M méd (min)": f"{d['big_m'].mean():.0f}",
        })
    partes += [_md(pd.DataFrame(t1)), ""]
    parou = df[df["status"] != "otimo"]
    if not parou.empty:
        partes += [
            "Instâncias que pararam no limite de tempo (todas as rodadas de r). Como custo e tempo "
            "valem menos que 1 ponto, uma solução de prioridade P tem objetivo em (P − 1, P]; se o "
            "limitante for ≤ P, nenhuma solução com prioridade maior existe e a prioridade máxima "
            "está provada.",
            "",
            _md(pd.DataFrame([{
                "instância": row["instancia"], "r": row["r"], "lojas": row["n_lojas_modelo"],
                "itens": row["n_itens"], "objetivo": f"{row['objetivo']:.4f}",
                "limitante": f"{row['limitante']:.4f}", "gap (%)": f"{100 * row['gap']:.2f}",
                "prioridade": row["prioridade"],
                "prioridade máxima provada": "sim" if row["limitante"] <= row["prioridade"] + 1e-9 else "não",
                "heurística = incumbente": "sim" if abs(row["objetivo"] - row["heur_objetivo"]) < 1e-6 else "não",
            } for _, row in parou.iterrows()])),
            "",
        ]

    partes += [f"## 2. Heurística × modelo exato (r = {config.R_PADRAO})", ""]
    t2 = []
    for tam in TAMANHOS:
        d = base[base["tamanho"] == tam]
        if d.empty:
            continue
        dif_obj = d["objetivo"] - d["heur_objetivo"]
        gap_h = dif_obj / d["objetivo"].where(d["objetivo"].abs() > 1e-9)
        t2.append({
            "tamanho": tam,
            "heurística = exato": f"{int((dif_obj.abs() < 1e-6).sum())}/{len(d)}",
            "mesma prioridade": f"{int((d['prioridade'] == d['heur_prioridade']).sum())}/{len(d)}",
            "pontos de prioridade perdidos (total)": int((d["prioridade"] - d["heur_prioridade"]).sum()),
            "custo a mais méd (US$)": f"{(d['heur_custo_total'] - d['custo_total']).mean():.2f}",
            "andando a mais méd (min)": f"{(d['heur_tempo_andando'] - d['tempo_andando']).mean():.2f}",
            "gap da heurística méd / máx (%)": f"{100 * gap_h.fillna(0).mean():.4f} / {100 * gap_h.fillna(0).max():.4f}",
            "tempo heurística méd / máx (s)": f"{d['heur_tempo_s'].mean():.3f} / {d['heur_tempo_s'].max():.3f}",
        })
    partes += [_md(pd.DataFrame(t2)), "",
               "Gap da heurística = (objetivo exato − objetivo heurística) ÷ objetivo exato.", ""]

    partes += [f"## 3. Mochila, cota e imposto (r = {config.R_PADRAO})", ""]
    t3 = []
    for tam in TAMANHOS:
        d = base[base["tamanho"] == tam]
        if d.empty:
            continue
        t3.append({
            "tamanho": tam,
            "orçamento < custo mínimo da lista": int((d["orcamento"] < d["custo_minimo_lista"]).sum()),
            "com item deixado de fora": int((d["itens_comprados"] < d["n_itens"]).sum()),
            "prioridade atendida méd (%)": f"{100 * (d['prioridade'] / d['prioridade_lista']).mean():.1f}",
            "pagam imposto": int((d["imposto"] > 0).sum()),
            "imposto méd quando paga (US$)": f"{d.loc[d['imposto'] > 0, 'imposto'].mean():.2f}"
                if (d["imposto"] > 0).any() else "—",
            "lojas visitadas méd": f"{d['lojas_visitadas'].mean():.1f}",
            "andando méd (min)": f"{d['tempo_andando'].mean():.1f}",
        })
    partes += [_md(pd.DataFrame(t3)), ""]

    partes += ["## 4. Polimento da rota", ""]
    t4 = []
    for tam in TAMANHOS:
        d = base[base["tamanho"] == tam]
        if d.empty:
            continue
        t4.append({
            "tamanho": tam,
            "exato: rotas encurtadas": int(d["polimento_aceito"].fillna(False).astype(bool).sum()),
            "exato: minutos economizados (total)":
                f"{(d['tempo_andando_antes_polimento'] - d['tempo_andando']).sum():.2f}",
            "heurística: rotas encurtadas": int(d["heur_polimento_aceito"].fillna(False).astype(bool).sum()),
            "heurística: minutos economizados (total)":
                f"{(d['heur_tempo_andando_antes_polimento'] - d['heur_tempo_andando']).sum():.2f}",
        })
    partes += [_md(pd.DataFrame(t4)), ""]

    sens = df[df["tamanho"].isin(["pequena", "media"])]
    if sens["r"].nunique() > 1:
        partes += ["## 5. Sensibilidade ao valor do minuto r (pequenas e médias)", ""]
        t5 = []
        ref = sens[sens["r"] == config.R_PADRAO].set_index("instancia")
        for (tam, r), d in sens.groupby(["tamanho", "r"], sort=True):
            d = d.set_index("instancia")
            mudou = (
                (d["custo_total"] - ref.loc[d.index, "custo_total"]).abs().gt(0.005)
                | (d["tempo_andando"] - ref.loc[d.index, "tempo_andando"]).abs().gt(1e-6)
            )
            t5.append({
                "tamanho": tam, "r (US$/min)": r, "instâncias": len(d),
                "prioridade méd": f"{d['prioridade'].mean():.2f}",
                "custo total méd (US$)": f"{d['custo_total'].mean():.2f}",
                "andando méd (min)": f"{d['tempo_andando'].mean():.2f}",
                "lojas visitadas méd": f"{d['lojas_visitadas'].mean():.2f}",
                "pagam imposto": int((d["imposto"] > 0).sum()),
                "solução difere de r = 0,25": int(mudou.sum()),
                "tempo exato méd (s)": f"{d['tempo_exato_s'].mean():.2f}",
            })
        t5 = pd.DataFrame(t5)
        t5["ordem"] = t5["tamanho"].map({t: n for n, t in enumerate(TAMANHOS)})
        t5 = t5.sort_values(["ordem", "r (US$/min)"]).drop(columns="ordem")
        piv = sens.pivot_table(index="instancia", columns="r", values="prioridade")
        n_prior = int((piv.nunique(axis=1) > 1).sum())
        partes += [_md(t5), "",
                   f"Instâncias em que a prioridade atendida mudou com r: {n_prior}. Pela escolha de λ, "
                   "gasto + tempo valem menos que 1 ponto de prioridade, então r só deveria "
                   "redistribuir entre gasto e caminhada entre soluções de mesma prioridade.", ""]
    inviaveis = df[~df["viavel"].astype(bool)]
    partes += [f"Soluções inviáveis na verificação independente: {len(inviaveis)}.", ""]
    return "\n".join(partes)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Experimentos da Fase 2 (100 instâncias + sensibilidade a r).")
    p.add_argument("--processos", type=int, default=1, help="instâncias resolvidas em paralelo")
    p.add_argument("--saida", type=Path, default=config.DIR_RESULTADOS)
    p.add_argument("--so-resumo", action="store_true", help="só refaz o resumo a partir do CSV")
    a = p.parse_args(argv)
    if a.so_resumo:
        df = pd.read_csv(a.saida / "resultados_fase2.csv")
    else:
        df = rodar(a.processos, a.saida)
    texto = resumo(df, a.processos if a.processos > 1 else None)
    (a.saida / "resumo_experimentos.md").write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
