# Resultados dos experimentos — Fase 2

Gerado por `python -m lesteshop.otimizacao.experimentos`. Base **fictícia** (`tipo_dado = sintetico`); os números servem para avaliar o modelo, não para decisões de compra.

Configuração: PuLP + CBC (1 thread por instância, 3 instâncias em paralelo), limite de 60 s (pequenas e médias) e 300 s (grandes); heurística como solução inicial; r = 0.25 US$/min, exceto na análise de sensibilidade.

Tempos são de relógio (wall clock), com as instâncias rodando em paralelo; a mediana é menos sensível a atrasos pontuais do sistema operacional ao iniciar o CBC.

## 1. Modelo exato por tamanho (r = 0.25)

| tamanho | instâncias | lojas no modelo (méd/máx) | itens (méd/máx) | variáveis (méd) | ótimo | limite de tempo | gap méd / máx (%) | tempo méd / mediana / máx (s) | M méd (min) |
|---|---|---|---|---|---|---|---|---|---|
| pequena | 40 | 4.3 / 5 | 4.3 / 6 | 48 | 40 | 0 | 0.000 / 0.000 | 0.02 / 0.02 / 0.06 | 358 |
| media | 35 | 9.7 / 14 | 7.0 / 10 | 156 | 34 | 1 | 0.112 / 3.911 | 1.91 / 0.08 / 60.10 | 412 |
| grande | 25 | 27.2 / 35 | 9.9 / 15 | 911 | 25 | 0 | 0.000 / 0.000 | 4.30 / 3.01 / 22.57 | 394 |

### Distribuição dos gaps das instâncias que atingiram o limite de tempo

| tamanho | r | rodadas | atingiram o limite | gap mín / mediana / méd / máx (%) | gap < 1% | 1% ≤ gap < 5% | gap ≥ 5% |
|---|---|---|---|---|---|---|---|
| pequena | 0.0 | 40 | 0 | — | 0 | 0 | 0 |
| pequena | 0.25 | 40 | 0 | — | 0 | 0 | 0 |
| pequena | 1.0 | 40 | 0 | — | 0 | 0 | 0 |
| media | 0.0 | 35 | 1 | 3.92 / 3.92 / 3.92 / 3.92 | 0 | 1 | 0 |
| media | 0.25 | 35 | 1 | 3.91 / 3.91 / 3.91 / 3.91 | 0 | 1 | 0 |
| media | 1.0 | 35 | 1 | 3.89 / 3.89 / 3.89 / 3.89 | 0 | 1 | 0 |
| grande | 0.25 | 25 | 0 | — | 0 | 0 | 0 |

Status, gap e tempo de cada rodada estão nas colunas `status`, `gap` e `tempo_exato_s` de `resultados_fase2.csv`.

Instâncias que pararam no limite de tempo (todas as rodadas de r). Como custo e tempo valem menos que 1 ponto, uma solução de prioridade P tem objetivo em (P − 1, P]; se o limitante for ≤ P, nenhuma solução com prioridade maior existe e a prioridade máxima está provada.

| instância | r | lojas | itens | objetivo | limitante | gap (%) | prioridade | prioridade máxima provada | heurística = incumbente |
|---|---|---|---|---|---|---|---|---|---|
| inst_075_media | 0.0 | 10 | 10 | 24.0935 | 25.0391 | 3.92 | 25 | não | sim |
| inst_075_media | 0.25 | 10 | 10 | 24.1008 | 25.0433 | 3.91 | 25 | não | sim |
| inst_075_media | 1.0 | 10 | 10 | 24.1212 | 25.0595 | 3.89 | 25 | não | sim |

## 2. Heurística × modelo exato (r = 0.25)

| tamanho | heurística = exato | mesma prioridade | pontos de prioridade perdidos (total) | custo a mais méd (US$) | andando a mais méd (min) | gap da heurística méd / máx (%) | tempo heurística méd / máx (s) |
|---|---|---|---|---|---|---|---|
| pequena | 40/40 | 40/40 | 0 | 0.00 | -0.00 | 0.0000 / 0.0000 | 0.001 / 0.006 |
| media | 35/35 | 35/35 | 0 | 0.00 | 0.00 | 0.0000 / 0.0000 | 0.006 / 0.014 |
| grande | 24/25 | 25/25 | 0 | 0.12 | -0.42 | 0.0001 / 0.0024 | 0.045 / 0.309 |

Gap da heurística = (objetivo exato − objetivo heurística) ÷ objetivo exato.

## 3. Mochila, cota e imposto (r = 0.25)

| tamanho | orçamento < custo mínimo da lista | com item deixado de fora | prioridade atendida méd (%) | pagam imposto | imposto méd quando paga (US$) | lojas visitadas méd | andando méd (min) |
|---|---|---|---|---|---|---|---|
| pequena | 20 | 27 | 87.6 | 12 | 186.76 | 2.3 | 38.8 |
| media | 18 | 24 | 92.3 | 13 | 288.96 | 4.9 | 50.8 |
| grande | 14 | 18 | 93.1 | 13 | 187.98 | 7.2 | 51.4 |

## 4. Polimento da rota

| tamanho | exato: rotas encurtadas | exato: minutos economizados (total) | heurística: rotas encurtadas | heurística: minutos economizados (total) |
|---|---|---|---|---|
| pequena | 0 | 0.00 | 0 | 0.00 |
| media | 0 | 0.00 | 0 | 0.00 |
| grande | 0 | 0.00 | 1 | 1.18 |

## 5. Sensibilidade ao valor do minuto r (pequenas e médias)

| tamanho | r (US$/min) | instâncias | prioridade méd | custo total méd (US$) | andando méd (min) | lojas visitadas méd | pagam imposto | solução difere de r = 0,25 | tempo exato méd (s) |
|---|---|---|---|---|---|---|---|---|---|
| pequena | 0.0 | 40 | 11.78 | 451.51 | 39.75 | 2.38 | 12 | 4 | 0.27 |
| pequena | 0.25 | 40 | 11.78 | 451.69 | 38.80 | 2.33 | 12 | 0 | 0.02 |
| pequena | 1.0 | 40 | 11.78 | 452.26 | 37.48 | 2.25 | 12 | 6 | 0.28 |
| media | 0.0 | 35 | 19.89 | 710.90 | 55.69 | 4.94 | 13 | 11 | 1.82 |
| media | 0.25 | 35 | 19.89 | 711.29 | 50.83 | 4.86 | 13 | 0 | 1.91 |
| media | 1.0 | 35 | 19.89 | 714.12 | 45.58 | 4.57 | 13 | 15 | 2.06 |

Instâncias em que a prioridade atendida mudou com r: 0. Pela escolha de λ, gasto + tempo valem menos que 1 ponto de prioridade, então r só deveria redistribuir entre gasto e caminhada entre soluções de mesma prioridade.

Soluções inviáveis na verificação independente: 0.
