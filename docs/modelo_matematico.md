# Modelo matemático — LesteShop, Fase 2

Traveling Purchaser Problem (TPP) com mochila, cota de isenção, imposto sobre o
excedente e janelas de tempo. O turista sai da Ponte da Amizade (nó 0), visita
algumas lojas de Ciudad del Este, compra os itens da lista que couberem no
orçamento e volta à Ponte. O TPP clássico (Laporte, Riera-Ledesma e
Salazar-González, 2003) exige comprar todos os itens; aqui, pela decisão tomada
com o professor, o modelo pode **deixar itens de fora** (estrutura de mochila), e
o valor de cada item é a prioridade 1–5 informada pelo turista.

Implementação: `src/lesteshop/otimizacao/` (modelo exato em `modelo.py`).
Todos os valores monetários estão em **US$** e todos os tempos em **minutos**
(horários contados a partir de 00:00).

## 1. Conjuntos

| Símbolo | Significado |
|---|---|
| M = {1, …, m} | lojas candidatas (após o pré-processamento da seção 7) |
| V = {0} ∪ M | nós; 0 = Ponte da Amizade (lado paraguaio) |
| A = {(i, j) ∈ V × V : i ≠ j} | arcos |
| K | itens da lista de compras |
| M_k ⊆ M | lojas que vendem o item k |
| K_i ⊆ K | itens da lista vendidos pela loja i |

## 2. Parâmetros

| Símbolo | Significado | Origem |
|---|---|---|
| p_ik | preço unitário do item k na loja i (menor oferta da loja) | `ofertas.preco_usd` |
| q_k | quantidade desejada | `lista_compras.quantidade` |
| v_k | prioridade (1 a 5) = valor do item | `lista_compras.prioridade` |
| c | cota de isenção disponível | `metadata.cota_disponivel_usd` |
| α | alíquota sobre o excedente (0,5) | `metadata.aliquota_excedente` |
| B | orçamento (preço + imposto); **B = c** se o turista não informar | `metadata.orcamento_usd` |
| t_ij | tempo a pé de i para j | seção 5 |
| s_i | permanência na loja i | `lojas.tempo_permanencia_min` (padrão 20) |
| [a_i, b_i] | janela da loja recortada pela do turista: a_i = max(abre_i, H⁰), b_i = min(fecha_i, H¹) | `lojas.abre`, `lojas.fecha` (padrões 07:00 e 16:00) |
| H⁰, H¹ | chegada e saída do turista **no lado paraguaio** da Ponte | `metadata.horario_chegada`, `horario_saida` |
| T_max = H¹ − H⁰ | tempo disponível na cidade | — |
| r | valor do minuto andando (padrão US$ 0,25/min) | parâmetro |
| λ | peso de custo e tempo na função objetivo | seção 4 |
| M | big-M das restrições de tempo | seção 6 |
| w_k, ω_k, W, Ω | peso e volume do item, limites de bagagem (opcionais, desligados por padrão) | `produtos.peso_kg`, `volume_l` |

## 3. Variáveis

| Variável | Domínio | Significado |
|---|---|---|
| x_ij | {0, 1} | o roteiro usa o arco (i, j) |
| z_i | {0, 1} | a loja i é visitada |
| u_ik | {0, 1}, só para i ∈ M_k | o item k é comprado na loja i |
| y_k | {0, 1} | o item k é comprado |
| G | ≥ 0 | gasto em produtos |
| E | ≥ 0 | excedente sobre a cota (o imposto é α·E) |
| τ_i | [a_i, b_i − s_i] | início do atendimento na loja i |
| R | [H⁰, H¹] | horário de volta à Ponte |

## 4. Função objetivo (uma única resolução)

```
max  Σ_k v_k·y_k  −  λ · ( G + α·E + r · Σ_(i,j)∈A t_ij·x_ij )

λ = 1 / (B + r·T_max + 1)
```

### 4.1 Interpretação de r

O termo entre parênteses é um **custo generalizado em US$**: o que o turista paga
(produtos + imposto) mais o tempo andando convertido em dólar. Com r = 0,25, o
turista aceita pagar até **US$ 0,25 a mais para andar 1 minuto a menos** (US$ 15
por hora de caminhada). Com r = 0, a caminhada é ignorada (ela só é limitada pela
janela de tempo); com r alto, o modelo prefere lojas próximas e menos paradas,
mesmo pagando mais.

### 4.2 Dedução de λ: a prioridade sempre domina

Seja C = G + α·E + r·Σ t_ij·x_ij o custo generalizado de uma solução viável.

1. **C ≥ 0**, porque G, E, r e t_ij são não negativos.
2. **G + α·E ≤ B** pela restrição de orçamento (R6).
3. **Σ t_ij·x_ij ≤ T_max**: a rota sai em H⁰ e volta em R ≤ H¹, e o tempo da rota é
   a caminhada mais as permanências e esperas (≥ 0). Logo a caminhada não passa
   de H¹ − H⁰.
4. Portanto 0 ≤ C ≤ B + r·T_max e, com λ = 1/(B + r·T_max + 1),

   **0 ≤ λ·C < 1.**

   (O "+1" garante a desigualdade estrita, inclusive quando B + r·T_max = 0.)

Agora tome duas soluções viáveis S₁ e S₂ com prioridades V₁ = Σ v_k·y_k > V₂.
Como as prioridades são inteiras, V₁ ≥ V₂ + 1, e então

```
f(S₁) = V₁ − λ·C₁ > V₁ − 1 ≥ V₂ ≥ V₂ − λ·C₂ = f(S₂).
```

Ou seja, **um ponto de prioridade sempre vale mais que qualquer diferença de
custo e tempo**. Custo e tempo só decidem entre soluções de mesma prioridade, e
aí o modelo escolhe a de menor custo generalizado. É o mesmo efeito de um
lexicográfico "prioridade primeiro", mas com uma única resolução. Dentro do
mesmo nível de prioridade, gasto e caminhada são trocados à taxa r (não é um
lexicográfico em três níveis; esse fica como melhoria futura).

Consequência útil para ler os resultados: uma solução de prioridade P tem
objetivo em (P − 1, P]. Se o limitante superior do solver for ≤ P, nenhuma
solução de prioridade maior existe.

### 4.3 Escala usada no solver

Multiplicar a função objetivo pela constante positiva K = 1/λ = B + r·T_max + 1
não muda o ótimo. O código resolve

```
max  K · Σ_k v_k·y_k − ( G + α·E + r·Σ t_ij·x_ij )
```

para evitar coeficientes muito pequenos (λ ≈ 10⁻⁴ nas instâncias de orçamento
alto) e relata o objetivo na escala original. O gap relativo é o mesmo nas duas
escalas.

## 5. Matriz de tempos

```
t_ij = haversine(i, j) × 1,3 ÷ 75 m/min
```

* **haversine**: distância geodésica entre as coordenadas (raio da Terra 6.371 km);
* **1,3**: fator de circuidade, a razão entre a distância pela rede de ruas e a
  distância em linha reta. Ballou, Rahardja e Sakai (2002) estimam esse fator para
  vários países. Adotamos 1,3 como valor típico de malha urbana; o valor fica em
  `config.FATOR_CIRCUIDADE` e deve ser confirmado com o professor;
* **75 m/min** = 4,5 km/h, velocidade de caminhada;
* lojas do **mesmo prédio** (mesmo `predio`, sem diferença de maiúsculas e acentos)
  levam **1 min** fixo. O valor `"Rua (loja de rua)"` não agrupa: lojas de rua usam a
  distância. Entre nós distintos o tempo mínimo é 1 min, o que mantém as
  restrições de tempo eliminando subrotas;
* a matriz é simétrica. Na base fictícia, os tempos vão de 1 a cerca de 38 min.

## 6. Restrições

```
(R1) Σ_{i∈M_k} u_ik = y_k                                ∀ k ∈ K     atribuição (o item inteiro em uma loja)
(R2) u_ik ≤ z_i                                           ∀ k, i ∈ M_k  só compra em loja visitada
     z_i ≤ Σ_{k∈K_i} u_ik                                 ∀ i ∈ M     só visita loja onde compra
(R3) Σ_{j∈V} x_ij = z_i ,  Σ_{j∈V} x_ji = z_i             ∀ i ∈ M     grau
     Σ_{j∈M} x_0j = Σ_{j∈M} x_j0 ≤ 1                                  a Ponte é saída e chegada
     z_i ≤ Σ_{j∈M} x_0j                                   ∀ i ∈ M     se visita alguma loja, sai da Ponte
(R4) G = Σ_k Σ_{i∈M_k} p_ik·q_k·u_ik                                  gasto
(R5) E ≥ G − c ,  E ≥ 0                                               excedente sobre a cota
(R6) G + α·E ≤ B                                                      orçamento (preço + imposto)
(R7) τ_j ≥ H⁰ + t_0j − M·(1 − x_0j)                       ∀ j ∈ M
     τ_j ≥ τ_i + s_i + t_ij − M·(1 − x_ij)                ∀ i ≠ j ∈ M
     R  ≥ τ_i + s_i + t_i0 − M·(1 − x_i0)                 ∀ i ∈ M
     a_i ≤ τ_i ≤ b_i − s_i ,  H⁰ ≤ R ≤ H¹                             janelas (limites das variáveis)
(R8) Σ_k w_k·q_k·y_k ≤ W ,  Σ_k ω_k·q_k·y_k ≤ Ω                       bagagem (opcional, desligada por padrão)
```

**Espera.** As restrições R7 usam "≥": se o turista chega antes de a loja abrir,
ele espera até a_i.

**Subrotas.** Como s_i + t_ij > 0, um ciclo entre lojas que não passe pela Ponte
exigiria τ estritamente crescente ao longo do ciclo, o que é impossível. As
restrições de tempo fazem o papel das restrições MTZ (Miller, Tucker e Zemlin,
1960).

**Imposto.** Basta a desigualdade linear R5, sem variável binária. Como α > 0 e
E aparece com sinal negativo na função objetivo, o ótimo tem E = max(0, G − c).
Mesmo assim, o imposto exibido é sempre **recalculado depois de resolver**,
α·max(0, G − c), para não depender das tolerâncias numéricas do solver.

**Mochila.** Nada obriga y_k = 1. Se o orçamento, a janela de tempo ou a bagagem
não comportam a lista, o modelo escolhe quais itens deixar de fora. A solução
vazia (não sair da Ponte) é sempre viável, então o modelo nunca é inviável.

### 6.1 Big-M

Usamos o menor valor da fórmula aprovada, calculado por instância e registrado
no resultado (`big_m`):

```
M = max_i b_i + max_i s_i + max_(i,j) t_ij − min_i a_i
```

com as janelas já recortadas pela janela do turista.

Validade: com x_ij = 0, cada restrição de R7 precisa ficar folgada para qualquer
valor das variáveis dentro dos seus limites.

* Entre lojas: τ_i + s_i + t_ij − τ_j ≤ (b_i − s_i) + s_i + t_ij − a_j ≤ max b + max t − min a ≤ M.
* Saindo da Ponte: H⁰ + t_0j − τ_j ≤ H⁰ + max t − a_j ≤ max t ≤ M, pois a_j ≥ H⁰.
* Voltando à Ponte: τ_i + s_i + t_i0 − M ≤ max b + max t − M = min a − max s ≤ H⁰ ≤ R. ✓

Nas 100 instâncias, M fica entre cerca de 160 e 580 min (coluna `big_m` de `data/resultados/resultados_fase2.csv`).

## 7. Pré-processamento (decisões aprovadas)

* Entram só as lojas que vendem pelo menos um item da lista.
* Lojas com `coordenada_pendente = true` ficam de fora. O aviso lista **quais itens
  da lista perderam essa opção de compra**.
* Oferta repetida da mesma loja para o mesmo produto: vale a de menor preço.
* Horários vazios recebem os padrões: abre 07:00, fecha 16:00, permanência 20 min.
* Uma loja cuja janela recortada não comporta a permanência (a_i + s_i > b_i) fica
  de fora, com aviso.
* Itens sem nenhuma oferta disponível não entram em K. Eles aparecem como "não
  comprados", com aviso.

### Hipóteses sobre o horário

* H⁰ e H¹ são horários **no lado paraguaio** da Ponte da Amizade: H⁰ é quando o
  turista já atravessou e começa a andar; H¹ é quando ele precisa estar de volta à
  cabeceira paraguaia.
* **A fila da aduana não é modelada.** O tempo de travessia e de fiscalização
  (que pode passar de uma hora em dias de movimento) deve ser descontado pelo
  turista ao informar H⁰ e H¹.
* A permanência s_i é por loja visitada e não depende de quantos itens são
  comprados nela.

## 8. Método de solução

1. **Heurística** (`heuristica.py`): construção gulosa em três ordens dos itens
   (prioridade e menor preço; prioridade ÷ menor preço; menor preço), com inserção
   da loja na melhor posição viável da rota. Depois, busca local: trocar a loja de
   um item, incluir um item, trocar um item comprado por um de fora (e reencher a
   mochila), e 2-opt/realocação na rota. Usa a mesma função objetivo do modelo.
2. **Modelo exato** (`modelo.py`): PuLP + CBC (1 thread), com a solução da heurística
   como solução inicial (*warm start*). Limite de 60 s nas instâncias pequenas e
   médias e 300 s nas grandes. São registrados status, gap, limitante, tempo, M e
   o tamanho do modelo.
3. **Polimento da rota** (`rota.py`), aplicado à solução do modelo e à da
   heurística: mantém as lojas e as compras e reotimiza só a **ordem de visita**,
   de forma exata (PuLP, TSP com janelas) quando há até 10 lojas, ou por
   2-opt/realocação acima disso. A nova ordem só é aceita se for viável e reduzir
   o tempo andando; em caso de empate, fica a ordem original. O tempo andando antes
   e depois do polimento é registrado.
4. A solução final nunca é pior que a da heurística: se o solver parar no limite
   com uma incumbente pior, vale a da heurística.

## 9. Saídas

Para cada solução (`resolver.py`, `solucao.descrever`): itens comprados com loja e
preço, itens deixados de fora, roteiro com horários de chegada e atendimento,
horário de volta, prioridade atendida, gasto em produtos, imposto, custo total,
situação da cota, tempo andando (antes e depois do polimento), peso e volume
totais da bagagem (sempre exibidos, mesmo com a restrição desligada) e avisos do
pré-processamento.

## Referências

* BALLOU, R. H.; RAHARDJA, H.; SAKAI, N. Selected country circuity factors for road
  travel distance estimation. *Transportation Research Part A: Policy and Practice*,
  v. 36, n. 9, p. 843–848, 2002.
* LAPORTE, G.; RIERA-LEDESMA, J.; SALAZAR-GONZÁLEZ, J.-J. A branch-and-cut algorithm
  for the undirected traveling purchaser problem. *Operations Research*, v. 51, n. 6,
  p. 940–951, 2003.
* MILLER, C. E.; TUCKER, A. W.; ZEMLIN, R. A. Integer programming formulation of
  traveling salesman problems. *Journal of the ACM*, v. 7, n. 4, p. 326–329, 1960.
