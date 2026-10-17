# Dicionário de dados — LesteShop, Fase 1

Todas as fontes (`FonteCSV`, `FonteComprasParaguai`, futura `FonteAPI`) entregam as
tabelas abaixo com as mesmas colunas. Valores monetários são sempre em **US$**;
o R$ só serve para exibição.

Convenções: `texto` = string UTF-8; `real` = número decimal; vazio = desconhecido
(nunca é preenchido com valor inventado). `tipo_dado` ∈ {`real`, `estimado`, `sintetico`}.

## lojas

| Campo | Tipo | Unidade / formato | Significado |
|---|---|---|---|
| loja_id | texto (PK) | `CP-<slug>` (coletada), `S01`… (semente), `SIN-L001`… (gerador) | Identificador único da loja |
| nome | texto | — | Nome exibido pela fonte |
| slug | texto | — | Identificador da loja na URL `/lojas/<slug>/` do Compras Paraguai |
| cidade | texto | — | Sempre `Ciudad del Este` (lojas de outras cidades são descartadas) |
| endereco | texto | — | Endereço como aparece na fonte |
| predio | texto | — | Shopping/galería/edificio extraído do endereço (ou preenchido à mão). Lojas no mesmo prédio terão deslocamento ≈ 0 na Fase 2 |
| latitude | real | graus decimais (WGS84) | Vazio se a fonte não tiver mapa |
| longitude | real | graus decimais (WGS84) | Vazio se a fonte não tiver mapa |
| coordenada_pendente | booleano | `true`/`false` | `true` quando falta latitude/longitude (completar em `data/lojas_complemento.csv`) |
| abre | texto | `HH:MM` | Horário de abertura (vazio se a fonte não informar) |
| fecha | texto | `HH:MM` | Horário de fechamento; deve ser maior que `abre` |
| tempo_permanencia_min | real | minutos | Tempo médio gasto dentro da loja (a fonte não informa; definido na Fase 2) |
| fonte | texto | — | `comprasparaguai.com.br`, `semente_manual` ou `gerador` |
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
