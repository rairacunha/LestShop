# Resultados dos experimentos — Fase 3 (regras fiscais)

Gerado por `python -m lesteshop.fiscal.experimentos`. Base **fictícia** (`tipo_dado = sintetico`). Modelo da Fase 2 sem mudanças, r = 0.25 US$/min; cota integral de US$ 500 (via terrestre) em todas as instâncias. Os limites quantitativos são verificados depois de otimizar e só geram alertas (`docs/legislacao_bagagem.md`).

## 1. Alertas por tamanho

| tamanho | instâncias | algum limite ultrapassado | perdem a cota | excesso de bebidas (regime comum) | excedem a cota (G > 500) | declaração necessária | unidades de outros bens méd / máx | litros de bebida máx |
|---|---|---|---|---|---|---|---|---|
| pequena | 40 | 0 | 0 | 0 | 12 | 12 | 3.2 / 6 | 2 |
| media | 35 | 0 | 0 | 0 | 13 | 13 | 5.6 / 9 | 2.75 |
| grande | 25 | 4 | 4 | 0 | 13 | 13 | 7.9 / 14 | 2 |
| total | 100 | 4 | 4 | 0 | 38 | 38 | 5.2 / 14 | 2.75 |

## 2. Instâncias com limite ultrapassado

| instância | itens comprados | limites | unidades de outros bens | gasto (US$) | imposto do modelo (US$) | imposto sem cota (US$) |
|---|---|---|---|---|---|---|
| inst_076_grande | 13 | outros_total | 11 | 548.28 | 24.14 | 274.14 |
| inst_078_grande | 15 | outros_total | 14 | 729.56 | 114.78 | 364.78 |
| inst_087_grande | 12 | outros_total | 11 | 924.46 | 212.23 | 462.23 |
| inst_091_grande | 11 | outros_total | 11 | 751.74 | 125.87 | 375.87 |

Nessas instâncias o modelo mantém a cesta (os limites não são restrição); pela norma, a bagagem perderia a cota e o imposto passaria a ser 50% de todo o gasto.

## 3. Conferência com a Fase 2

* Instâncias com cota de US$ 500 na Fase 2: 100; com a mesma solução (prioridade, custo total e tempo andando) agora: 100.
* Nenhuma instância tinha cota diferente de US$ 500.

Soluções inviáveis na verificação independente: 0.
