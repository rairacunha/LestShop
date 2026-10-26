# Base fictícia LesteShop — teste da Fase 1

**Todos os dados são FICTÍCIOS** (tipo_dado = "sintetico"). Nomes de lojas e prédios
foram inventados; coordenadas foram sorteadas na área central de Ciudad del Este;
preços são plausíveis, mas não correspondem a nenhuma loja real. Não use para
decisões de compra.

## Base completa (data/raw/)
- lojas.csv — 50 lojas em 8 prédios/galerias fictícios (lojas do mesmo
  prédio ficam a poucos metros, para testar deslocamento quase zero)
- produtos.csv — 73 produtos em 14 categorias,
  com peso e volume (inclui a coluna extra preco_base_usd, usada só para gerar)
- ofertas.csv — 613 ofertas; todo produto tem pelo menos 2 lojas
- pontos_partida.csv — nó 0 (Ponte da Amizade)
- cotacoes.csv — cotação fictícia US$ 1 = R$ 5.14

## 100 instâncias (data/instances/)
- 40 pequenas (5 lojas, 10 produtos), 35 médias (15 lojas, 40 produtos),
  25 grandes (40 lojas, até 70 produtos)
- Cada pasta tem lojas, produtos, ofertas, pontos_partida, **lista_compras.csv**
  (3 a 15 itens desejados, com prioridade 1–5) e metadata.json (seed, densidade,
  cota disponível, orçamento, horários de chegada e saída)
- resumo_instancias.csv lista todas lado a lado
- Os cenários variam de propósito: algumas listas cabem na cota, outras excedem;
  a cota disponível às vezes é menor que 500 (parte já usada no mês).

Regenerar: `python scripts/gerar_base_ficticia.py` (seed fixa 2026, resultado idêntico).
