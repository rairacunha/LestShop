"""Experimentos da Fase 3: em quantas instâncias a cesta ótima dispara algum alerta fiscal.

Os limites quantitativos não restringem o modelo, então cada instância é resolvida
como na Fase 2 (r = 0,25; heurística → exato com warm start → polimento) e a cesta
escolhida é verificada depois. A única mudança de entrada é a cota: agora sempre a
cota integral da tabela de regras (US$ 500), em vez da cota disponível de 500, 300
ou 150 que vinha no ``metadata.json``. As instâncias que tinham cota de US$ 500 na
Fase 2 servem de conferência: a solução tem de ser a mesma.

Saídas em ``data/resultados/fase3/``:

* ``resultados_fase3.csv``: uma linha por instância (colunas da Fase 2 + situação fiscal);
* ``solucoes/r0.25/<instancia>.json``: solução final com o bloco ``fiscal``;
* ``resumo_fase3.md``: contagem dos alertas por tamanho e conferência com a Fase 2.

Uso::

    python -m lesteshop.fiscal.experimentos --processos 3
    python -m lesteshop.fiscal.experimentos --so-resumo
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from ..otimizacao import config
from ..otimizacao.experimentos import (TAMANHOS, _aquecer, _md, _rotulo_r, executar,
                                       listar_instancias)

DIR_SAIDA = config.DIR_RESULTADOS / "fase3"
CSV_FASE2 = config.DIR_RESULTADOS / "resultados_fase2.csv"
R = config.R_PADRAO


def _usado(fiscal: dict, regra_id: str) -> float:
    return next((s["usado"] for s in fiscal["limites"] if s["regra_id"] == regra_id), 0.0)


def executar_fiscal(pasta: Path, dir_saida: Path) -> dict:
    linha = executar(pasta, R, dir_saida)
    sol = json.loads((dir_saida / "solucoes" / _rotulo_r(R) / f"{linha['instancia']}.json")
                     .read_text(encoding="utf-8"))
    f = sol["fiscal"]
    linha.update({
        "excede_cota": linha["gasto_produtos"] > f["cota_usd"] + 1e-9,
        "limites_ultrapassados": ";".join(f["limites_ultrapassados"]),
        "n_limites_ultrapassados": len(f["limites_ultrapassados"]),
        "perde_cota": f["perde_cota"],
        "imposto_sem_cota": f["imposto_sem_cota_usd"],
        "excesso_regime_comum": ";".join(f["excesso_regime_comum"]),
        "declaracao_necessaria": f["declaracao_necessaria"],
        "algum_alerta_limite": bool(f["limites_ultrapassados"]),
        "unidades_outros": _usado(f, "outros_total"),
        "max_identicos_outros": _usado(f, "outros_identicos"),
        "unidades_pequeno_valor": _usado(f, "pequeno_valor_total"),
        "litros_bebidas": _usado(f, "bebidas"),
    })
    return linha


def _tarefa(args):
    pasta, dir_saida = args
    linha = executar_fiscal(Path(pasta), Path(dir_saida))
    print(f"{linha['instancia']}: {linha['status']}, alertas de limite: "
          f"{linha['limites_ultrapassados'] or '—'}", flush=True)
    return linha


def rodar(processos: int = 1, dir_saida: Path = DIR_SAIDA,
          instancias: list[Path] | None = None) -> pd.DataFrame:
    instancias = instancias or listar_instancias()
    tarefas = sorted(((str(p), str(dir_saida)) for p in instancias), key=lambda t: "grande" not in t[0])
    if processos > 1:
        with ProcessPoolExecutor(processos, initializer=_aquecer) as ex:
            linhas = list(ex.map(_tarefa, tarefas))
    else:
        _aquecer()
        linhas = [_tarefa(t) for t in tarefas]
    df = pd.DataFrame(linhas).sort_values("instancia").reset_index(drop=True)
    dir_saida.mkdir(parents=True, exist_ok=True)
    df.to_csv(dir_saida / "resultados_fase3.csv", index=False)
    return df


def _sim(s: pd.Series) -> pd.Series:
    return s.fillna(False).astype(str).str.lower().isin(("true", "1"))


def resumo(df: pd.DataFrame, fase2: pd.DataFrame | None = None) -> str:
    partes = [
        "# Resultados dos experimentos — Fase 3 (regras fiscais)",
        "",
        "Gerado por `python -m lesteshop.fiscal.experimentos`. Base **fictícia** "
        "(`tipo_dado = sintetico`). Modelo da Fase 2 sem mudanças, r = "
        f"{R} US$/min; cota integral de US$ 500 (via terrestre) em todas as instâncias. Os limites "
        "quantitativos são verificados depois de otimizar e só geram alertas "
        "(`docs/legislacao_bagagem.md`).",
        "",
        "## 1. Alertas por tamanho",
        "",
    ]
    linhas = []
    for tam in TAMANHOS + ("total",):
        d = df if tam == "total" else df[df["tamanho"] == tam]
        if d.empty:
            continue
        perde = _sim(d["perde_cota"])
        linhas.append({
            "tamanho": tam, "instâncias": len(d),
            "algum limite ultrapassado": int(_sim(d["algum_alerta_limite"]).sum()),
            "perdem a cota": int(perde.sum()),
            "excesso de bebidas (regime comum)": int(d["excesso_regime_comum"].fillna("").astype(str)
                                                     .str.contains("bebidas").sum()),
            "excedem a cota (G > 500)": int(_sim(d["excede_cota"]).sum()),
            "declaração necessária": int(_sim(d["declaracao_necessaria"]).sum()),
            "unidades de outros bens méd / máx": f"{d['unidades_outros'].mean():.1f} / {d['unidades_outros'].max():g}",
            "litros de bebida máx": f"{d['litros_bebidas'].max():g}",
        })
    partes += [_md(pd.DataFrame(linhas)), ""]

    acima = df[_sim(df["algum_alerta_limite"])]
    partes += ["## 2. Instâncias com limite ultrapassado", ""]
    if acima.empty:
        partes += ["Nenhuma.", ""]
    else:
        partes += [_md(pd.DataFrame([{
            "instância": r["instancia"], "itens comprados": r["itens_comprados"],
            "limites": r["limites_ultrapassados"], "unidades de outros bens": f"{r['unidades_outros']:g}",
            "gasto (US$)": f"{r['gasto_produtos']:.2f}", "imposto do modelo (US$)": f"{r['imposto']:.2f}",
            "imposto sem cota (US$)": f"{r['imposto_sem_cota']:.2f}" if pd.notna(r["imposto_sem_cota"]) else "—",
        } for _, r in acima.iterrows()])), "",
            "Nessas instâncias o modelo mantém a cesta (os limites não são restrição); pela norma, "
            "a bagagem perderia a cota e o imposto passaria a ser 50% de todo o gasto.", ""]

    if fase2 is not None and not fase2.empty:
        f2 = fase2[fase2["r"] == R].set_index("instancia")
        comum = df[df["instancia"].isin(f2.index)].set_index("instancia")
        cota500 = f2.loc[comum.index, "cota"] == 500
        mesma = (
            (comum["prioridade"] == f2.loc[comum.index, "prioridade"])
            & ((comum["custo_total"] - f2.loc[comum.index, "custo_total"]).abs() < 0.005)
            & ((comum["tempo_andando"] - f2.loc[comum.index, "tempo_andando"]).abs() < 1e-6)
        )
        outras = comum[~cota500]
        partes += [
            "## 3. Conferência com a Fase 2",
            "",
            f"* Instâncias com cota de US$ 500 na Fase 2: {int(cota500.sum())}; com a mesma solução "
            f"(prioridade, custo total e tempo andando) agora: {int(mesma[cota500].sum())}.",
            f"* Instâncias com cota de US$ 300 ou 150 na Fase 2: {len(outras)}. Com a cota integral, "
            f"{int((~mesma[~cota500]).sum())} mudaram de solução; prioridade atendida média de "
            f"{f2.loc[outras.index, 'prioridade'].mean():.2f} para {outras['prioridade'].mean():.2f}, "
            f"imposto médio de US$ {f2.loc[outras.index, 'imposto'].mean():.2f} para "
            f"US$ {outras['imposto'].mean():.2f}." if len(outras) else
            "* Nenhuma instância tinha cota diferente de US$ 500.",
            "",
        ]
    partes += [f"Soluções inviáveis na verificação independente: {int((~_sim(df['viavel'])).sum())}.", ""]
    return "\n".join(partes)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Experimentos da Fase 3 (alertas fiscais nas 100 instâncias).")
    p.add_argument("--processos", type=int, default=1, help="instâncias resolvidas em paralelo")
    p.add_argument("--saida", type=Path, default=DIR_SAIDA)
    p.add_argument("--so-resumo", action="store_true", help="só refaz o resumo a partir do CSV")
    a = p.parse_args(argv)
    df = pd.read_csv(a.saida / "resultados_fase3.csv") if a.so_resumo else rodar(a.processos, a.saida)
    fase2 = pd.read_csv(CSV_FASE2) if CSV_FASE2.exists() else None
    texto = resumo(df, fase2)
    (a.saida / "resumo_fase3.md").write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
