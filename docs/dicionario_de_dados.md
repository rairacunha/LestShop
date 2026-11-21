# Dicionário de dados — LesteShop (Fases 1 a 4)

Todas as fontes (`FonteCSV`, `FonteComprasParaguai`, futura `FonteAPI`) entregam as
tabelas abaixo com as mesmas colunas. Valores monetários são sempre em **US$**;
o R$ só serve para exibição.

Convenções: `texto` = string UTF-8; `real` = número decimal; vazio = desconhecido
(nunca é preenchido com valor inventado). `tipo_dado` ∈ {`real`, `estimado`, `sintetico`}.

## lojas

| Campo | Tipo | Unidade / formato | Significado |
|---|---|---|---|
| loja_id | texto (PK) | `CP-<slug>` (coletada), `L001`… (base fictícia), `S01`… (semente dos testes), `SIN-L001`… (gerador) | Identificador único da loja |
| nome | texto | — | Nome exibido pela fonte |
| slug | texto | — | Identificador da loja na URL `/lojas/<slug>/` do Compras Paraguai |
| cidade | texto | — | Sempre `Ciudad del Este` (lojas de outras cidades são descartadas) |
| endereco | texto | — | Endereço como aparece na fonte |
| predio | texto | — | Shopping/galería/edificio extraído do endereço (ou preenchido à mão). Lojas no mesmo prédio terão deslocamento ≈ 0 na Fase 2 |
| latitude | real | graus decimais (WGS84) | Vazio se a fonte não tiver mapa |
| longitude | real | graus decimais (WGS84) | Vazio se a fonte não tiver mapa |
| coordenada_pendente | booleano | `true`/`false` | `true` quando falta latitude/longitude (completar em `data/lojas_complemento.csv`) |
| abre | texto | `HH:MM` | Horário de abertura (vazio se a fonte não informar; a Fase 2 usa 07:00) |
| fecha | texto | `HH:MM` | Horário de fechamento; deve ser maior que `abre` (vazio: a Fase 2 usa 16:00) |
| tempo_permanencia_min | real | minutos | Tempo médio gasto dentro da loja (a fonte não informa; a Fase 2 usa 20 min quando vazio) |
| fonte | texto | — | `comprasparaguai.com.br`, `ficticio (gerado para teste da Fase 1)`, `semente_manual` ou `gerador` |
| tipo_dado | texto | — | Ver convenções |

## produtos

| Campo | Tipo | Unidade / formato | Significado |
|---|---|---|---|
| produto_id | texto (PK) | `CP-<id do modelo>`, `P01`…, `SIN-P001`… | Identificador único |
| nome | texto | — | Nome do modelo (título `<h1>` da página do modelo) |
| categoria | texto | — | Último nível da trilha (breadcrumb) da página ou informado na coleta |
| url_modelo | texto | URL | Página do modelo `/<slug>_<id>/` |
| peso_kg | real | kg | "Peso Bruto" da tabela de especificações (vazio se não houver) |
| volume_l | real | litros | Produto das "Dimensões" da embalagem ÷ 1000 (cm³ → L); vazio se não houver |
| desconto_brasil_pct | real | fração (0 a 1) | Percentual exibido na página do modelo como "~X% mais barato que no Brasil" (0,28 = 28%). Vazio se a página não mostrar; nunca estimado |
| tipo_dado | texto | — | Ver convenções |

## ofertas

| Campo | Tipo | Unidade / formato | Significado |
|---|---|---|---|
| loja_id | texto (FK → lojas) | — | Loja que vende |
| produto_id | texto (FK → produtos) | — | Produto vendido |
| titulo_oferta | texto | — | Título do anúncio na loja (pode diferir do nome do modelo) |
| codigo_loja | texto | — | Código do produto na loja ("Cód:"), se houver |
| preco_usd | real | US$ | Preço anunciado em dólar; > 0. **Base de todos os cálculos** |
| preco_brl | real | R$ | Preço em reais mostrado pela fonte (cotação da própria loja/site) |
| data_coleta | texto | `AAAA-MM-DD` | Dia da coleta. Ofertas reais com mais de 30 dias geram alerta |
| fonte | texto | — | Origem da oferta |
| tipo_dado | texto | — | Ver convenções |

No SQLite a tabela tem também `oferta_id` (inteiro autoincremento, PK técnica).
A matriz loja × produto é esparsa: nem toda loja vende todo produto.

## pontos_partida

| Campo | Tipo | Unidade | Significado |
|---|---|---|---|
| id | inteiro (PK) | — | `0` = Ponte da Amizade, cabeceira paraguaia (nó 0 do roteiro) |
| nome | texto | — | Descrição do ponto |
| latitude, longitude | real | graus decimais | Posição (estimada no mapa) |

## catalogo_modelos

| Campo | Tipo | Unidade | Significado |
|---|---|---|---|
| modelo_id | texto (PK) | `CP-<id>` | Mesmo id usado em `produtos.produto_id` quando o modelo é coletado |
| nome | texto | — | Derivado do slug da URL (o sitemap não traz o nome) |
| url | texto | URL | Página do modelo |
| categoria | texto | — | Vazio (o sitemap não informa) |
| data_atualizacao | texto | `AAAA-MM-DD` | Dia em que o modelo entrou ou mudou no catálogo |

`data/catalogo_meta.json` guarda a data da última atualização e o total de modelos novos/removidos.

## cotacoes

| Campo | Tipo | Unidade | Significado |
|---|---|---|---|
| data | texto (PK) | `AAAA-MM-DD` | Dia da PTAX usada (último dia útil ≤ dia pedido) |
| valor_brl_por_usd | real | R$/US$ | PTAX de venda (último boletim do dia) |
| fonte | texto | — | Banco Central do Brasil — Olinda/PTAX |
| data_consulta | texto | `AAAA-MM-DD` | (só no SQLite) dia em que a API foi consultada; controla o cache de 1 dia |

## Tabelas auxiliares (só no SQLite)

* **descartes_coleta** (`data`, `termo`, `url_modelo`, `loja_slug`, `cidade`, `motivo`): uma
  linha por oferta descartada na coleta por ser de fora de Ciudad del Este. Alimenta o
  resumo "ofertas descartadas por cidade".

## Arquivos de complemento manual

* **data/lojas_complemento.csv** (`loja_id`, `latitude`, `longitude`, `predio`, `observacao`):
  coordenadas copiadas do Google Maps e prédios corrigidos à mão. É aplicado ao gravar e ao
  recriar o banco, e sobrevive a novas coletas.

## Arquivos extras das instâncias de teste (`data/instances/inst_*`)

Vêm da base fictícia e trazem parâmetros que **só serão usados nas Fases 2 e 3**; a Fase 1
apenas os guarda e valida.

**lista_compras.csv**

| Campo | Tipo | Significado |
|---|---|---|
| produto_id | texto (FK → produtos da instância) | Item que o turista quer comprar |
| nome | texto | Nome do produto (cópia, para leitura) |
| quantidade | inteiro | Unidades desejadas (hoje sempre 1) |
| prioridade | inteiro 1–5 | Importância do item para o turista (5 = mais importante) |

**metadata.json**

| Campo | Unidade | Significado |
|---|---|---|
| nome, tamanho, seed, densidade | — | Identificação e parâmetros de geração |
| n_lojas, n_produtos, n_ofertas, n_itens_lista | — | Tamanho real da instância |
| orcamento_usd | US$ | Quanto o turista pode gastar |
| custo_minimo_lista_usd | US$ | Soma dos menores preços dos itens da lista (sem deslocamento) |
| lista_excede_cota | booleano | `custo_minimo_lista_usd` > cota integral da tabela de regras (US$ 500) |
| horario_chegada, horario_saida | HH:MM | Janela de tempo do turista em Ciudad del Este |
| data_geracao, tipo_dado | — | Sempre `sintetico` |

Fase 3: os campos `cota_disponivel_usd` e `aliquota_excedente` foram removidos. A cota e
a alíquota vêm de `data/regras_fiscais.csv` (abaixo); se um `metadata.json` antigo ainda
tiver esses campos, eles são ignorados, com aviso.

**Coluna extra em produtos.csv:** `preco_base_usd` (preço de referência usado só para gerar
as ofertas fictícias; não é dado de mercado).

## Regras fiscais (Fase 3)

**`data/regras_fiscais.csv`** — uma linha por regra e vigência; para cada `regra_id`
vale a linha mais recente com `vigencia_inicio` ≤ data de referência (padrão: hoje).

| Campo | Significado |
|---|---|
| regra_id | `cota_terrestre`, `aliquota_rte`, `bebidas`, `cigarros`, `charutos`, `fumo`, `pequeno_valor_total`, `pequeno_valor_identicos`, `outros_total`, `outros_identicos` |
| tipo_limite | `valor` (US$), `quantidade` (unidades, maços, gramas), `litros` ou `aliquota` (fração, só `aliquota_rte`) |
| categoria_fiscal | categoria a que a regra se aplica (`todas` para a cota) |
| contagem | `total` (soma da categoria) ou `identicos` (cada produto separadamente) |
| limite, unidade | valor do limite e unidade |
| via | via de transporte (o projeto usa `terrestre`) |
| valor_unitario_min_usd, valor_unitario_max_usd | faixa de preço unitário coberta (mínimo inclusivo, máximo exclusivo; vazio = sem limite) |
| consequencia | `rte_excedente` (50% sobre o que passa da cota), `regime_comum` (o excesso não pode ser regularizado como bagagem) ou `perde_cota` (RTE sobre tudo, sem a cota) |
| descricao, fonte, vigencia_inicio | texto, norma e dispositivo, data de início (AAAA-MM-DD) |

**`data/categorias_fiscais.csv`** — editável à mão.

| Campo | Significado |
|---|---|
| categoria | valor de `produtos.categoria` |
| produto_id | vazio = vale para a categoria toda; preenchido = só esse produto (tem precedência) |
| categoria_fiscal | `outros`, `bebidas_alcoolicas`, `cigarros`, `charutos_cigarrilhas`, `fumo` |
| conteudo_por_unidade | litros de bebida, maços ou gramas por unidade (`produtos.volume_l` é a embalagem, não o conteúdo) |
| observacao | texto livre |

**Bloco `fiscal` de `descrever()`**: `cota_usd` e `fonte_cota`, `premissa` (cota integral),
`limites` (por regra: `usado`, `limite`, `unidade`, `situacao` = `abaixo`/`no_limite`/`acima`,
`consequencia`, `fonte`, produto mais repetido nas regras de idênticos), `limites_ultrapassados`,
`perde_cota`, `imposto_modelo_usd`, `imposto_sem_cota_usd` (α·G quando a cota é perdida),
`excesso_regime_comum`, `declaracao_necessaria`, `alertas` e `avisos`.

## Resultados da Fase 3 (`data/resultados/fase3/resultados_fase3.csv`)

Uma linha por instância (r = 0,25), com as mesmas colunas de `resultados_fase2.csv` (a
coluna `cota` é sempre 500) e mais: `excede_cota`, `limites_ultrapassados`
(regras separadas por `;`), `n_limites_ultrapassados`, `algum_alerta_limite`,
`perde_cota`, `imposto_sem_cota`, `excesso_regime_comum`, `declaracao_necessaria`,
`unidades_outros`, `max_identicos_outros`, `unidades_pequeno_valor` e `litros_bebidas`.

## Resultados da Fase 2 (`data/resultados/resultados_fase2.csv`)

Uma linha por (instância, r). Valores em US$ e minutos. Formulação em
[`modelo_matematico.md`](modelo_matematico.md).

| Campo | Significado |
|---|---|
| instancia, tamanho, r | Instância e valor do minuto andando (US$/min) |
| n_lojas | Lojas reais da instância (`metadata.json`) |
| n_lojas_modelo, n_lojas_excluidas | Lojas candidatas após o pré-processamento / excluídas (coordenada pendente ou fora da janela) |
| n_itens | Itens da lista |
| cota, orcamento, custo_minimo_lista | Cota usada na rodada (US$ 500, da tabela de regras; a primeira rodada da Fase 2 usava 500, 300 ou 150 do `metadata.json`), orçamento B, soma dos menores preços da lista |
| lambda, big_m | λ = 1/(B + r·T_max + 1) e o big-M usado |
| n_variaveis, n_restricoes | Tamanho do modelo exato |
| status | `otimo` ou `viavel (limite de tempo)` |
| gap, limitante, tempo_exato_s, limite_s | Gap relativo, limitante superior do objetivo, tempo do CBC e limite usado |
| origem_final | `exato`, ou `heuristica (...)` se a heurística ficou melhor no limite de tempo |
| objetivo | Σ v·y − λ·(G + α·E + r·tempo andando) da solução final |
| prioridade, prioridade_lista | Prioridade atendida / soma das prioridades da lista |
| itens_comprados | Itens comprados |
| gasto_produtos, imposto, custo_total | G, α·max(0, G − c) recalculado, G + imposto |
| tempo_andando, tempo_andando_antes_polimento | Minutos andando depois / antes do polimento da rota |
| polimento, polimento_aceito | Método (`exato`, `2-opt`, `nenhum`) e se encurtou a rota |
| lojas_visitadas, retorno_min | Paradas e horário de volta à Ponte (minutos desde 00:00) |
| peso_kg, volume_l | Totais da bagagem |
| heur_* | Os mesmos indicadores para a solução da heurística (`heur_tempo_s` = tempo da heurística) |
| tempo_total_s | Tempo total da rodada (heurística + exato + polimentos) |
| viavel | Verificação independente de viabilidade das duas soluções |

## Fase 4 — aplicativo e consulta sob demanda

### `data/catalogo_app.json` (catálogo curado do app)

Lista fixa de produtos populares que a busca do app oferece primeiro. Cada item de
`produtos`:

| Campo | Significado |
|---|---|
| `id` | identificador estável do item no catálogo (ex.: `iphone-17-256`) |
| `nome` | nome mostrado na busca; começa pela marca, como no site |
| `termo` | termo de busca no Compras Paraguai, usado quando não há `url_modelo` |
| `categoria` | categoria do projeto, a mesma de `data/categorias_fiscais.csv` |
| `url_modelo` | (opcional) página do modelo no site; a consulta vai direto a ela |
| `conteudo_por_unidade` | (opcional) litros por garrafa, para o limite de bebidas |

### `data/cache/consulta.db` (cache da consulta, não versionado)

Tabela `consultas` (`item_id`, `gravado_em` em segundos desde 1970, `dados` em JSON). Para
cada item consultado: produto, lojas, ofertas e `consultado_em`. Também guarda as buscas
de modelos no site (`item_id` começando por `busca:`). **Validade: 6 horas.** As páginas de
loja têm cache permanente em `data/cache/lojas/`.

### `data/coletas/<AAAA-MM-DD>/` (base guardada)

Mesmo formato das tabelas `lojas`, `produtos`, `ofertas` (e `descartes`), um conjunto por
dia. Recebe a coleta em lote (`python -m lesteshop.data.coletar ... --navegador`) **e** todo
item consultado ao vivo no app. A base guardada do app usa, de cada (loja, produto), a
oferta da coleta mais recente; depois, descarta o **preço atípico** (menor que a metade da
mediana do produto, com 3 ofertas ou mais), com aviso.

### Campos que passaram a vir do site (página da loja, JSON-LD `Store`)

* `lojas.latitude` / `lojas.longitude`: coordenadas publicadas pelo site;
  `lojas_complemento.csv` só para lojas sem coordenada ou com coordenada errada.
* `lojas.abre` / `lojas.fecha`: horário de segunda a sexta (`openingHours`, ex.
  `Mo-Fr 06:30-17:00`); vazio → padrão comercial 07:00–16:00. O site informa em horário
  de Brasília.

### Cotação mostrada no app

`app.base.cotacao_do_site()`: mediana de `preco_brl / preco_usd` das ofertas reais (a
cotação do próprio Compras Paraguai; R$ 5,95 na coleta de 20/11/2026). Sem ofertas reais,
a PTAX. Só para exibição: os cálculos continuam em US$.
