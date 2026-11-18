"""Verificação da cesta escolhida frente às regras fiscais (Fase 3).

Os limites quantitativos **não restringem o modelo** (decisão aprovada): a
otimização da Fase 2 roda sem mudanças e, depois, a cesta escolhida é comparada
com cada limite:

    Σ_{k ∈ categoria} q_k · c_k · y_k  comparado com  L_categoria

em que q_k é o número de unidades da oferta k (comprada inteira ou não comprada) e
c_k o conteúdo por unidade (litros de bebida, maços, gramas; 1 para os demais bens).
Regras de contagem ``identicos`` comparam cada produto separadamente.

Consequências quando um limite é ultrapassado (``docs/legislacao_bagagem.md``):

* ``perde_cota`` (bens dos incisos V e VI): a bagagem vai para o RTE **sem a cota**,
  e o alerta mostra o imposto sem cota, α·G, ao lado do imposto do modelo;
* ``regime_comum`` (bebidas e tabaco): o excesso não pode ser regularizado como
  bagagem; só alerta, sem recomendar que o turista deixe de comprar.

A declaração (e-DBV) é necessária quando G > cota ou quando algum limite é
ultrapassado (IN RFB 1.059/2010, art. 6º, VIII e IX).
"""

from __future__ import annotations

from dataclasses import dataclass

from .regras import Regra, RegrasFiscais

TOL = 1e-9

PREMISSA_PERIODICIDADE = (
    "Cada rota é tratada como uma viagem nova: assume-se que a cota não foi usada no intervalo "
    "de 1 (um) mês anterior à entrada no Brasil (Portaria MF 440/2010, art. 7º, § 4º). "
    "Se a cota já tiver sido usada, toda a compra é tributada a 50%."
)


@dataclass(frozen=True)
class ItemCesta:
    produto_id: str
    nome: str
    categoria_fiscal: str
    quantidade: int                       # q_k: unidades da oferta (lote)
    preco_unitario: float                 # US$ por unidade
    conteudo_por_unidade: float | None = None


def _medida(item: ItemCesta, regra: Regra) -> float | None:
    """Quanto o item conta para a regra (None = conteúdo necessário e não informado)."""
    if item.conteudo_por_unidade is not None:
        return item.quantidade * item.conteudo_por_unidade
    if regra.tipo_limite == "litros":
        return None
    return float(item.quantidade)


def _situacao(usado: float, limite: float) -> str:
    if usado > limite + TOL:
        return "acima"
    if abs(usado - limite) <= TOL:
        return "no_limite"
    return "abaixo"


def _fmt(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def _avaliar_regra(regra: Regra, itens: list[ItemCesta]) -> tuple[dict | None, list[str]]:
    avisos: list[str] = []
    pool = [it for it in itens if it.categoria_fiscal == regra.categoria_fiscal
            and regra.cobre_valor(it.preco_unitario)]
    if not pool:
        return None, avisos
    medidas: dict[str, float] = {}
    nomes: dict[str, str] = {}
    for it in pool:
        m = _medida(it, regra)
        if m is None:
            avisos.append(f"{it.nome} ({it.produto_id}): conteúdo em {regra.unidade} não informado em "
                          "categorias_fiscais.csv; não entrou na conta de '{0}'.".format(regra.descricao))
            continue
        medidas[it.produto_id] = medidas.get(it.produto_id, 0.0) + m
        nomes[it.produto_id] = it.nome
    if regra.contagem == "total":
        usado, produto = sum(medidas.values()), None
    else:
        produto = max(medidas, key=lambda p: (medidas[p], p)) if medidas else None
        usado = medidas.get(produto, 0.0) if produto else 0.0
    situacao = _situacao(usado, regra.limite)
    return {
        "regra_id": regra.regra_id, "descricao": regra.descricao,
        "categoria_fiscal": regra.categoria_fiscal, "contagem": regra.contagem,
        "usado": round(usado, 4), "limite": regra.limite, "unidade": regra.unidade,
        "situacao": situacao, "consequencia": regra.consequencia, "fonte": regra.fonte,
        "produto_id": produto, "produto": nomes.get(produto) if produto else None,
        "itens": sorted(nomes),
    }, avisos


def _alerta_limite(s: dict, aliquota: float, gasto: float) -> str:
    alvo = f" ({s['produto']})" if s["contagem"] == "identicos" and s["produto"] else ""
    base = (f"Limite ultrapassado — {s['descricao']}{alvo}: {_fmt(s['usado'])} {s['unidade']} "
            f"para um limite de {_fmt(s['limite'])} {s['unidade']} ({s['fonte']}).")
    if s["consequencia"] == "perde_cota":
        return (base + " Pela norma, a bagagem perde a cota de isenção e vai para o regime de "
                f"tributação especial sobre todo o valor: imposto estimado de US$ {aliquota * gasto:.2f}.")
    if s["consequencia"] == "regime_comum":
        excesso = s["usado"] - s["limite"]
        return (base + f" O excesso ({_fmt(round(excesso, 4))} {s['unidade']}) não pode ser "
                "regularizado como bagagem: vai para o regime comum de importação.")
    return base


def verificar(
    itens: list[ItemCesta],
    regras: RegrasFiscais,
    gasto_produtos: float,
    aliquota: float,
    imposto_modelo: float,
) -> dict:
    """Situação fiscal da cesta: limites, alertas, imposto sem cota e declaração."""
    limites: list[dict] = []
    avisos: list[str] = []
    for regra in regras.limites:
        s, av = _avaliar_regra(regra, itens)
        avisos += av
        if s is not None:
            limites.append(s)
    acima = [s for s in limites if s["situacao"] == "acima"]
    alertas = [_alerta_limite(s, aliquota, gasto_produtos) for s in acima]
    perde_cota = any(s["consequencia"] == "perde_cota" for s in acima)
    excede_cota = gasto_produtos > regras.cota_usd + TOL
    motivos = []
    if excede_cota:
        motivos.append(f"o gasto (US$ {gasto_produtos:.2f}) passa da cota de US$ {regras.cota_usd:.2f}")
    if acima:
        motivos.append("há limite quantitativo ultrapassado")
    declaracao = bool(motivos)
    if declaracao:
        alertas.append(
            "Declaração necessária: preencher a e-DBV e passar pelo canal \"bens a declarar\" "
            f"porque {' e '.join(motivos)} (IN RFB 1.059/2010, art. 6º, VIII e IX; IN RFB 1.385/2013, art. 2º)."
        )
    return {
        "via": regras.via,
        "data_referencia": regras.data_referencia.isoformat(),
        "cota_usd": regras.cota_usd,
        "fonte_cota": regras.cota.fonte,
        "premissa": PREMISSA_PERIODICIDADE,
        "limites": limites,
        "limites_ultrapassados": [s["regra_id"] for s in acima],
        "perde_cota": perde_cota,
        "imposto_modelo_usd": round(imposto_modelo, 2),
        "imposto_sem_cota_usd": round(aliquota * gasto_produtos, 2) if perde_cota else None,
        "excesso_regime_comum": [s["regra_id"] for s in acima if s["consequencia"] == "regime_comum"],
        "declaracao_necessaria": declaracao,
        "alertas": alertas,
        "avisos": avisos,
    }
