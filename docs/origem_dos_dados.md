# Origem dos dados — LesteShop, Fase 1

## Classificação

| tipo_dado | Significado | Onde aparece |
|---|---|---|
| `real` | Lido de uma fonte pública no dia indicado em `data_coleta` | Coletas do Compras Paraguai (`data/coletas/<data>/`) |
| `estimado` | Valor plausível, sem fonte direta, a conferir | Peso e volume dos produtos da semente dos testes (`tests/fixtures/semente/`) |
| `sintetico` | Inventado para testes e experimentos | Toda a base fictícia de `data/raw/`; as 100 instâncias de `data/instances/`; a semente dos testes |

Nenhum dado inventado é marcado como `real`.

## De onde vem cada dado

| Dado | Fonte | Observações |
|---|---|---|
| Ofertas (preço US$, R$, título, código) | Página de modelo do [Compras Paraguai](https://www.comprasparaguai.com.br) (`/<slug>_<id>/`) | Coleta sob demanda, só dos modelos pedidos |
| Lojas (nome, endereço, cidade, mapa, horário) | Página da loja (`/lojas/<slug>/`) | Cache permanente em `data/cache/lojas/` |
| Prédio/shopping | Extraído do endereço por expressão regular (`predio.py`) | Pode errar; corrigir em `data/lojas_complemento.csv` |
| Coordenadas ausentes | Google Maps, preenchidas à mão em `data/lojas_complemento.csv` | Campo `observacao` registra a origem |
| Desconto em relação ao Brasil (`desconto_brasil_pct`) | Aviso "~X% mais barato que no Brasil" da página do modelo | **Estimativa do próprio Compras Paraguai, sem metodologia divulgada** (não se sabe com quais preços brasileiros, de quando, nem se inclui impostos). Vazio quando a página não mostra; não estimamos nem completamos valores. Vazio em toda a base fictícia |
| Peso e volume | Tabela de especificações da página do modelo ("Peso Bruto", "Dimensões" da embalagem) | Vazio quando não existe; nunca estimado automaticamente |
| Catálogo de modelos | Sitemap indicado no `robots.txt` | Nome derivado do slug da URL |
| Cotação do dólar | PTAX de venda do Banco Central (API Olinda) | Só para exibir R$ |
| Ponte da Amizade (nó 0) | Posição aproximada da cabeceira paraguaia, lida no mapa | `estimado` |
| Base fictícia (`data/raw/`, `data/instances/inst_*`) | `scripts/gerar_base_ficticia.py`, seed 2026 | Lojas, prédios e produtos inventados ("(fictícia)" no nome); coordenadas sorteadas no microcentro; preços ±15% em torno de um preço-base com viés por loja; cotação fictícia R$ 5,14 |
| Semente dos testes (`tests/fixtures/semente/`) | Criada à mão para os testes automáticos | Lojas fictícias ("Loja Semente …"); preços sintéticos em torno de valores de mercado; produtos são modelos reais com peso/volume estimados |

## Boa conduta na coleta

* `robots.txt` respeitado (URLs proibidas interrompem a coleta; `Crawl-delay` respeitado se for maior que 10 s).
* Pelo menos 10 s entre requisições ao mesmo host.
* User-Agent `LesteShop/0.1 (projeto academico de Pesquisa Operacional II; ...)`. A variável de ambiente `LESTESHOP_CONTATO` acrescenta um contato.
* Cache diário das páginas em `data/cache/paginas/<data>/`: a mesma página não é baixada de novo no mesmo dia.
* Somente os termos/URLs pedidos; nunca o site inteiro (o catálogo usa apenas o sitemap).
* Se o HTML mudar, a coleta para com `ErroEstruturaHTML` e nada é gravado.

## Limitações conhecidas

* **A Fase 1 foi concluída com dados fictícios.** O coletor real está pronto e testado com
  páginas imitadas, mas a primeira coleta real ainda não foi feita (depende da verificação
  anti-robô, item 0). Nenhum preço desta base deve ser usado para decidir compras.

0. **Proteção anti-robô do site (Cloudflare).** Em 17/10/2026 o Compras Paraguai passou a
   responder HTTP 403 com `cf-mitigated: challenge` a qualquer acesso automático, inclusive ao
   `robots.txt`. O LesteShop não contorna essa proteção: a coleta abre um navegador visível
   (`--navegador`), o usuário resolve a verificação e só então as páginas são baixadas,
   dentro da mesma janela, em volume mínimo. Consequências: a coleta exige uma pessoa
   presente, não roda em servidores nem no GitHub Actions, e pode deixar de funcionar se o
   site endurecer a proteção. Não há acordo formal com o site; para uso fora do contexto
   acadêmico seria preciso autorização ou uma API oficial (`FonteAPI`).

1. **Preços podem estar desatualizados.** O Compras Paraguai mostra preços capturados
   automaticamente dos sites das lojas; o preço no balcão pode ser diferente. Por isso
   toda oferta tem `data_coleta`, e ofertas reais com mais de 30 dias geram alerta.
2. **Lojas do mesmo grupo são tratadas como lojas distintas**, como aparecem na fonte
   (ex.: duas lojas com o mesmo WhatsApp ou a mesma razão social). Na Fase 2 isso pode
   superestimar a quantidade de opções; se ficarem no mesmo prédio, o deslocamento entre
   elas será quase zero.
3. **A cotação oficial (PTAX) difere da cotação das lojas.** O `preco_brl` da oferta usa a
   cotação do site/loja; a conversão do sistema usa a PTAX de venda. Como os cálculos são
   feitos em US$ (inclusive a cota de isenção, que é em US$), a diferença só afeta a
   exibição em R$.
4. **Parser baseado em padrões do site, não em classes CSS.** A extração usa os padrões de
   URL (`/<slug>_<id>/`, `/lojas/<slug>/`) e os prefixos `US$`/`R$`. As fixtures de teste
   foram escritas à mão (o ambiente de desenvolvimento não tinha acesso ao site); conferir
   com páginas reais via `python -m lesteshop.data.salvar_fixtures`.
5. **Cidade da loja** vem do endereço da página da loja (ou da própria oferta, quando o site
   mostra). Se não for possível identificá-la e não houver coordenadas dentro de Ciudad del
   Este, a loja é descartada (postura conservadora).
6. **Coordenadas**: o retângulo de validação de Ciudad del Este é aproximado
   (lat −25,60 a −25,42; lon −54,75 a −54,597) e propositalmente exclui Foz do Iguaçu.
7. **Horário de funcionamento e tempo de permanência** raramente aparecem na fonte; ficam
   vazios nos dados reais.
8. **Nome no catálogo** vem do slug da URL (sem acentos e com maiúsculas aproximadas).
