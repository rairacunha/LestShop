"""Recálculo da rota durante o passeio (autorizado em 23/11/2026).

Só funciona com a localização do aparelho ativa e dentro de Ciudad del Este. O turista
marca as lojas em que já comprou; o app resolve de novo o **mesmo modelo** para os
produtos que faltam, saindo de onde ele está, no horário atual, e voltando à Ponte da
Amizade.

Como o modelo não muda:

* o nó 0 continua sendo o ponto de partida e de chegada do modelo; só a **ida** (linha 0
  da matriz de tempos) passa a sair da posição atual, e a **volta** (coluna 0) continua
  indo para a Ponte. O modelo trata cada sentido como um arco separado, então a matriz
  não precisa ser simétrica;
* a cota que sobra é a cota menos o que já foi comprado. Assim o imposto do recálculo é
  o imposto que falta pagar: α·max(0, G_feito + G_resto − cota) − α·max(0, G_feito − cota).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace

import numpy as np

from ..otimizacao.distancias import matriz_tempos
from ..otimizacao.instancia import Instancia

# Retângulo aproximado do município de Ciudad del Este (graus). O lado leste para antes do
# Rio Paraná (a cabeceira paraguaia da Ponte fica em −54,6033), para não aceitar quem
# está em Foz do Iguaçu.
CDE_LAT = (-25.585, -25.440)
CDE_LON = (-54.720, -54.599)

# Paraguai: UTC−3 o ano todo desde outubro de 2024 (fim do horário de verão).
FUSO_PARAGUAI = dt.timezone(dt.timedelta(hours=-3), "PYT")


def em_ciudad_del_este(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return CDE_LAT[0] <= lat <= CDE_LAT[1] and CDE_LON[0] <= lon <= CDE_LON[1]


def agora_no_paraguai() -> dt.datetime:
    return dt.datetime.now(FUSO_PARAGUAI)


def compras_feitas(d: dict, feitas: set[str]) -> list[dict]:
    """Compras das paradas marcadas como feitas (loja_id)."""
    return [c for p in d["roteiro"] if p["loja_id"] in feitas for c in p["compras"]]


def instancia_do_passeio(inst: Instancia, d: dict, feitas: set[str], lat: float, lon: float,
                         agora_min: float) -> tuple[Instancia, float]:
    """Instância com os produtos que faltam, saindo da posição atual às ``agora_min``.

    ``inst`` é a instância do cálculo original (preços do site, sem acréscimo).
    Devolve (instância, gasto já feito em US$)."""
    comprados = {c["produto_id"] for c in compras_feitas(d, feitas)}
    k_novo = {k: n for n, k in enumerate(k for k, it in enumerate(inst.itens) if it.produto_id not in comprados)}
    idx = {it.produto_id: k for k, it in enumerate(inst.itens)}
    feito = 0.0
    no = {l.loja_id: i for i, l in enumerate(inst.lojas, start=1)}
    for p in d["roteiro"]:
        if p["loja_id"] in feitas:
            for c in p["compras"]:
                feito += inst.preco[(no[p["loja_id"]], idx[c["produto_id"]])] * c["quantidade"]
    itens = [inst.itens[k] for k in k_novo]
    # Ida: da posição atual até cada loja. Volta: de cada loja até a Ponte (como antes).
    ida = matriz_tempos([(lat, lon)] + [(l.latitude, l.longitude) for l in inst.lojas],
                        [None] + [l.predio for l in inst.lojas])[0]
    # Só as lojas em que ainda dá para chegar e ser atendido antes de fecharem e voltar à
    # Ponte no horário (nós renumerados; o modelo exige abre ≤ fecha − permanência).
    abertas = [i for i, l in enumerate(inst.lojas, start=1)
               if max(agora_min + ida[i], l.abre) + l.permanencia <= l.fecha
               and max(agora_min + ida[i], l.abre) + l.permanencia + inst.t[i, 0] <= inst.saida]
    i_novo = {i: n for n, i in enumerate(abertas, start=1)}
    lojas = [replace(inst.lojas[i - 1], abre=max(inst.lojas[i - 1].abre, agora_min)) for i in abertas]
    preco = {(i_novo[i], k_novo[k]): v for (i, k), v in inst.preco.items() if k in k_novo and i in i_novo}
    nos = [0] + abertas
    t = inst.t[np.ix_(nos, nos)].copy()
    t[0, :] = ida[nos]
    novo = replace(inst, itens=itens, preco=preco, t=t, lojas=lojas, chegada=float(agora_min),
                   cota=max(0.0, inst.cota - feito), avisos=[])
    return novo, feito


def totais_do_passeio(feito: float, d_resto: dict, inst: Instancia, acrescimo: float = 0.0) -> dict:
    """Gasto já feito + o que falta, com o imposto da compra inteira (sobre o valor com o
    acréscimo da forma de pagamento). ``inst`` é a instância original (cota integral)."""
    feito_nf = feito * (1 + acrescimo)
    resto = d_resto["resumo"]["gasto_produtos"]
    total = feito_nf + resto
    imposto = inst.aliquota * max(0.0, total - inst.cota)
    return {"feito": feito_nf, "resto": resto, "gasto": total, "imposto": imposto,
            "custo_total": total + imposto, "excedente": max(0.0, total - inst.cota)}
