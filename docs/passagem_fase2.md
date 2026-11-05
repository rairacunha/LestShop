# Passagem para a Fase 2 — LesteShop

Documento de contexto para quem continua o projeto (pessoa ou novo chat).

## Situação ao fim da Fase 1 (05/11/2026)

* Fase 1 **concluída com base fictícia** (`tipo_dado = "sintetico"`), no `main` deste repositório.
* `data/raw/`: 50 lojas, 73 produtos, 613 ofertas, `pontos_partida.csv` (nó 0 = Ponte da
  Amizade) e cotação fictícia (US$ 1 = R$ 5,14). Gerada por `scripts/gerar_base_ficticia.py`
  (seed 2026, reprodutível).
* `data/instances/inst_001…inst_100`: 40 pequenas (5 lojas × 10 produtos), 35 médias
  (15 × 40), 25 grandes (40 × 70). Cada uma tem `lojas.csv`, `produtos.csv`, `ofertas.csv`,
  `pontos_partida.csv`, **`lista_compras.csv`** (produto_id, nome, quantidade, prioridade 1–5)
  e **`metadata.json`** (cota_disponivel_usd, aliquota_excedente = 0,5, orcamento_usd,
  custo_minimo_lista_usd, horario_chegada, horario_saida, n_lojas real...).
* `pytest`: 186 passam, 4 pulados (dependem do navegador e de páginas reais do site).
* Coleta real do Compras Paraguai: código pronto (`--navegador`, o usuário resolve a
  verificação anti-robô), **nunca executada no site real**. A Fase 2 usa a base fictícia.

## Regras de trabalho

* **Modelo cascata:** fazer apenas a fase pedida. O que for de outra fase vai para
  `docs/pendencias.md`, sem implementar.
* Respostas e documentação em português; código seguindo o estilo de `src/lesteshop/data/`.
* Dados inventados nunca são marcados como `real`.
* Commits no `main` de `rairacunha/LestShop`.

## Decisões já tomadas com o professor (ver `docs/pendencias.md`)

* Problema base: **Traveling Purchaser Problem** (Laporte, Riera-Ledesma e
  Salazar-González, 2003) — escolher em quais lojas comprar cada item e a rota a partir do
  nó 0, voltando a ele.
* **Orçamento é opcional.** Se informado, é limite rígido de gasto (preço + imposto). Se
  não informado, o teto é a própria cota (US$ 500).
* **Quando o orçamento não comporta a lista, o modelo deixa itens de fora** (mochila), em
  vez de declarar inviável.
* **Prioridade 1–5 é o valor v_i** do item na função objetivo: max Σ v_i · x_i.
* Cota de isenção: US$ 500 por via terrestre a cada 30 dias; **50% de imposto sobre o
  excedente**. A cota disponível de cada instância está no `metadata.json` (500, 300 ou 150).
  Todos os cálculos em **US$**.
* Lojas no mesmo `predio` têm deslocamento ≈ 0.
* Nos experimentos, usar o **número real de lojas** do `metadata.json` (10 instâncias têm
  menos que o nominal). Imposto em 64 das 100 instâncias é intencional. Em 52 o orçamento
  é menor que o custo mínimo da lista (é aí que a mochila atua).
* Tamanho grande = 40 lojas × 70 produtos, sem variantes artificiais.
* **Melhorias futuras, NÃO implementar agora:** "favorito" com pesos lexicográficos;
  desempate pela economia em relação ao Brasil (`desconto_brasil_pct`).

## Pontos em aberto para a Fase 2 (confirmar com o usuário antes de decidir)

* Função objetivo combinada: como pesar prioridade dos itens × custo (preço + imposto) ×
  deslocamento/tempo (objetivo lexicográfico, ponderado ou restrição).
* Matriz de distâncias/tempos: distância geodésica (haversine) × velocidade a pé, ou outra.
* Uso da janela de tempo (`horario_chegada`/`horario_saida`, `abre`/`fecha`,
  `tempo_permanencia_min`).
* Solver: PuLP/CBC, OR-Tools ou outro; formulação exata para pequenas/médias e heurística
  para grandes?
* Peso/volume (`peso_kg`, `volume_l`) como restrição de bagagem: sim ou não.
