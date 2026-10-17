"""Gerador de instâncias sintéticas para os experimentos da Fase 2.

Exemplo::

    python -m lesteshop.data.generator --size pequena --seed 42
    python -m lesteshop.data.generator --size grande --seed 7 --densidade 0.3 --base banco

Cada instância vai para data/instances/<nome>/ com lojas.csv, produtos.csv,
ofertas.csv, pontos_partida.csv e metadata.json. Todas as linhas são marcadas
como tipo_dado = "sintetico", mesmo quando derivadas de lojas/produtos reais.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, esquema
from .sources.fonte_csv import FonteCSV
from .validator import validar

TAMANHOS: dict[str, tuple[int, int]] = {
    "pequena": (5, 10),
    "media": (15, 40),
    "grande": (40, 150),
}
_ALIASES = {"média": "media", "p": "pequena", "m": "media", "g": "grande"}

# Microcentro de Ciudad del Este, perto da Ponte da Amizade (onde ficam os shoppings).
_MICROCENTRO = {"lat": (-25.5170, -25.5040), "lon": (-54.6170, -54.6045)}


def carregar_base(origem: str = "semente") -> dict[str, pd.DataFrame]:
    """``semente`` (data/raw) ou ``banco`` (data/lesteshop.db)."""
    if origem == "semente":
        fonte = FonteCSV(config.DIR_RAW)
        base = fonte.carregar_tudo()
        base["pontos_partida"] = fonte.carregar_pontos_partida()
        return base
    if origem == "banco":
        from .database import carregar_tabelas, conectar
        return carregar_tabelas(conectar(config.CAMINHO_BANCO))
    raise ValueError(f"Origem de base desconhecida: {origem!r} (use 'semente' ou 'banco').")


def _preco_base(base: dict[str, pd.DataFrame]) -> pd.Series:
    return base["ofertas"].groupby("produto_id")["preco_usd"].median()


def gerar_instancia(
    tamanho: str,
    seed: int,
    densidade: float = 0.5,
    variacao: float = 0.15,
    base: dict[str, pd.DataFrame] | None = None,
    origem_base: str = "semente",
    data_referencia: str | None = None,
) -> dict:
    """Gera uma instância. Mesma base + mesmos parâmetros + mesma seed = mesma instância.

    * ``densidade``: fração das lojas que vende cada produto (0 < d <= 1);
    * ``variacao``: preços uniformes em preço-base × (1 ± variacao).
    """
    tamanho = _ALIASES.get(tamanho, tamanho)
    if tamanho not in TAMANHOS:
        raise ValueError(f"Tamanho inválido: {tamanho!r}. Use {', '.join(TAMANHOS)}.")
    if not 0 < densidade <= 1:
        raise ValueError("A densidade deve estar no intervalo (0, 1].")
    if not 0 <= variacao < 1:
        raise ValueError("A variação de preço deve estar no intervalo [0, 1).")
    n_lojas, n_produtos = TAMANHOS[tamanho]
    base = base or carregar_base(origem_base)
    rng = np.random.default_rng(seed)

    lojas_base = base["lojas"].sort_values("loja_id").reset_index(drop=True)
    precos = _preco_base(base)
    produtos_base = base["produtos"][base["produtos"]["produto_id"].isin(precos.index)]
    produtos_base = produtos_base.sort_values("produto_id").reset_index(drop=True)
    if data_referencia is None:
        data_referencia = str(base["ofertas"]["data_coleta"].max())

    # --- lojas ------------------------------------------------------------------
    escolhidas = rng.permutation(len(lojas_base))[:n_lojas]
    lojas = lojas_base.iloc[sorted(escolhidas)].copy()
    predios = sorted(p for p in lojas_base["predio"].dropna().unique())
    extras = []
    for k in range(n_lojas - len(lojas)):
        predio = predios[rng.integers(len(predios))] if predios and rng.random() < 0.6 else f"Galería Sintética {k // 4 + 1:02d}"
        extras.append({"loja_id": f"SIN-L{k + 1:03d}", "nome": f"Loja Sintética {k + 1:03d}",
                       "slug": f"loja-sintetica-{k + 1:03d}", "cidade": config.CIDADE_ALVO,
                       "endereco": None, "predio": predio, "fonte": "gerador"})
    lojas = pd.concat([lojas, pd.DataFrame(extras)], ignore_index=True)

    # Coordenadas: lojas do mesmo prédio ficam juntas (±20 m); sem coordenada -> sorteio no microcentro.
    centro_predio: dict[str, tuple[float, float]] = {}
    for r in lojas_base.dropna(subset=["latitude", "longitude", "predio"]).itertuples():
        centro_predio.setdefault(r.predio, (r.latitude, r.longitude))
    lat, lon = [], []
    for r in lojas.itertuples():
        if pd.notna(r.latitude) and pd.notna(r.longitude):
            lat.append(r.latitude); lon.append(r.longitude)
            continue
        if isinstance(r.predio, str) and r.predio not in centro_predio:
            centro_predio[r.predio] = (rng.uniform(*_MICROCENTRO["lat"]), rng.uniform(*_MICROCENTRO["lon"]))
        if isinstance(r.predio, str):
            c_lat, c_lon = centro_predio[r.predio]
            lat.append(c_lat + rng.uniform(-0.0002, 0.0002)); lon.append(c_lon + rng.uniform(-0.0002, 0.0002))
        else:
            lat.append(rng.uniform(*_MICROCENTRO["lat"])); lon.append(rng.uniform(*_MICROCENTRO["lon"]))
    lojas["latitude"] = np.round(lat, 6)
    lojas["longitude"] = np.round(lon, 6)
    lojas["coordenada_pendente"] = False
    lojas["abre"] = lojas["abre"].fillna("07:00")
    lojas["fecha"] = lojas["fecha"].fillna("16:00")
    sem_tempo = lojas["tempo_permanencia_min"].isna()
    lojas.loc[sem_tempo, "tempo_permanencia_min"] = rng.integers(10, 31, int(sem_tempo.sum())).astype(float)
    lojas["fonte"] = lojas["fonte"].fillna("gerador")
    lojas["tipo_dado"] = "sintetico"

    # --- produtos -------------------------------------------------------------------
    escolhidos = rng.permutation(len(produtos_base))[:n_produtos]
    produtos = produtos_base.iloc[sorted(escolhidos)].copy()
    produtos["preco_base_usd"] = produtos["produto_id"].map(precos)
    variantes = []
    for k in range(n_produtos - len(produtos)):
        origem = produtos_base.iloc[rng.integers(len(produtos_base))]
        variantes.append({
            "produto_id": f"SIN-P{k + 1:03d}",
            "nome": f"{origem['nome']} (variante sintética {k + 1})",
            "categoria": origem["categoria"], "url_modelo": None,
            "peso_kg": origem["peso_kg"], "volume_l": origem["volume_l"],
            "preco_base_usd": round(float(precos[origem["produto_id"]]) * rng.uniform(0.7, 1.3), 2),
        })
    produtos = pd.concat([produtos, pd.DataFrame(variantes)], ignore_index=True)
    produtos["tipo_dado"] = "sintetico"

    # --- ofertas: matriz loja x produto esparsa ----------------------------------------
    ids_lojas = lojas["loja_id"].tolist()
    k_lojas = max(1, int(np.floor(densidade * n_lojas + 0.5)))
    ofertas = []
    for p in produtos.itertuples():
        for i in sorted(rng.choice(n_lojas, size=k_lojas, replace=False)):
            ofertas.append((ids_lojas[i], p.produto_id, p.preco_base_usd))
    vendem = {o[0] for o in ofertas}
    for i, loja_id in enumerate(ids_lojas):  # toda loja precisa vender algo
        if loja_id not in vendem:
            p = produtos.iloc[rng.integers(len(produtos))]
            ofertas.append((loja_id, p["produto_id"], p["preco_base_usd"]))
    fatores = rng.uniform(1 - variacao, 1 + variacao, len(ofertas))
    ofertas_df = pd.DataFrame({
        "loja_id": [o[0] for o in ofertas],
        "produto_id": [o[1] for o in ofertas],
        "titulo_oferta": None,
        "codigo_loja": None,
        "preco_usd": np.round([o[2] * f for o, f in zip(ofertas, fatores)], 2),
        "preco_brl": None,
        "data_coleta": data_referencia,
        "fonte": "gerador",
        "tipo_dado": "sintetico",
    }).sort_values(["produto_id", "loja_id"]).reset_index(drop=True)

    produtos = produtos.drop(columns="preco_base_usd")
    lojas = esquema.padronizar(lojas, "lojas")[esquema.COLUNAS["lojas"]]
    produtos = esquema.padronizar(produtos, "produtos")[esquema.COLUNAS["produtos"]]
    ofertas_df = esquema.padronizar(ofertas_df, "ofertas")[esquema.COLUNAS["ofertas"]]
    validar(lojas, produtos, ofertas_df, hoje=max(dt.date.today(), dt.date.fromisoformat(data_referencia))).levantar_se_invalido()

    return {
        "lojas": lojas,
        "produtos": produtos,
        "ofertas": ofertas_df,
        "pontos_partida": esquema.padronizar(base["pontos_partida"], "pontos_partida"),
        "metadata": {
            "nome": f"{tamanho}_seed{seed}",
            "tamanho": tamanho,
            "n_lojas": n_lojas,
            "n_produtos": n_produtos,
            "n_ofertas": len(ofertas_df),
            "seed": seed,
            "densidade": densidade,
            "densidade_efetiva": round(len(ofertas_df) / (n_lojas * n_produtos), 4),
            "variacao_preco": variacao,
            "base": origem_base,
            "data_referencia_precos": data_referencia,
            "data_geracao": dt.datetime.now().isoformat(timespec="seconds"),
        },
    }


def salvar_instancia(instancia: dict, pasta: str | Path | None = None) -> Path:
    pasta = Path(pasta or config.DIR_INSTANCIAS / instancia["metadata"]["nome"])
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in ("lojas", "produtos", "ofertas", "pontos_partida"):
        instancia[nome].to_csv(pasta / f"{nome}.csv", index=False)
    (pasta / "metadata.json").write_text(json.dumps(instancia["metadata"], ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    return pasta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera instâncias sintéticas do LesteShop.")
    parser.add_argument("--size", "--tamanho", dest="tamanho", required=True,
                        help="pequena (5x10), media (15x40) ou grande (40x150)")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--densidade", type=float, default=0.5, help="fração de lojas que vende cada produto")
    parser.add_argument("--variacao", type=float, default=0.15, help="variação de preço em torno do preço-base")
    parser.add_argument("--base", choices=("semente", "banco"), default="semente")
    parser.add_argument("--saida", help="pasta de saída (padrão: data/instances/<tamanho>_seed<seed>)")
    args = parser.parse_args(argv)
    inst = gerar_instancia(args.tamanho, args.seed, args.densidade, args.variacao, origem_base=args.base)
    pasta = salvar_instancia(inst, args.saida)
    m = inst["metadata"]
    print(f"Instância '{m['nome']}' gerada em {pasta}: {m['n_lojas']} lojas, {m['n_produtos']} produtos, "
          f"{m['n_ofertas']} ofertas (densidade efetiva {m['densidade_efetiva']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
