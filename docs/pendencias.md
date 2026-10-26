# Pendências para as próximas fases

Itens percebidos durante a Fase 1 que **não** foram implementados por pertencerem a
outras fases do modelo cascata.

## Fase 2 — Modelo de otimização (TPP)

* **Instâncias de teste prontas** em `data/instances/inst_001…inst_100`, com lista de compras,
  prioridade, cota, orçamento e janela de tempo. Observações encontradas na validação:
  * em **52 das 100** instâncias o orçamento é menor que o custo mínimo da lista (o gerador
    sorteia orçamento entre 60% e 140% do custo): o modelo precisa decidir se o orçamento é
    restrição rígida (instância inviável) ou se pode deixar itens de fora usando a prioridade;
  * em **64 das 100** a lista excede a cota disponível (vai haver imposto);
  * **10** instâncias têm menos lojas que o tamanho nominal (ex.: 33 em vez de 40), porque
    lojas sem ofertas são descartadas;
  * as grandes têm **70 produtos** (a base tem 73), não 150 como na especificação; para
    150 produtos use `python -m lesteshop.data.generator --size grande`, que cria variantes.
* `lista_compras.csv` e os parâmetros de cenário (`metadata.json`) foram definidos pela base
  fictícia, não pela Fase 1: validar com o professor antes de formular o modelo.

* Formular e resolver o Traveling Purchaser Problem (Laporte, Riera-Ledesma e
  Salazar-González, 2003) sobre `lojas`, `produtos`, `ofertas` e `pontos_partida`.
* Matriz de distâncias/tempos entre lojas e a Ponte da Amizade (nó 0). Lojas com o mesmo
  `predio` devem ter deslocamento ≈ 0.
* Definir valores padrão para `tempo_permanencia_min`, `abre` e `fecha` quando a fonte não
  informa (hoje ficam vazios nos dados reais; o gerador usa 07:00–16:00 e 10–30 min).
* Decidir como tratar lojas com `coordenada_pendente = true` (excluir, ou exigir o
  preenchimento em `data/lojas_complemento.csv` antes de otimizar).
* Escolher qual oferta usar quando a mesma loja anuncia o mesmo modelo mais de uma vez
  (hoje todas são guardadas).
* Usar `peso_kg`/`volume_l` como restrição de capacidade (bagagem), se o professor quiser.

## Fase 3 — Regras fiscais

* Cálculo da cota de isenção da Receita Federal (US$ 500 por via terrestre a cada 30 dias)
  e do imposto de 50% sobre o excedente, sempre em US$.
* Limites por quantidade/tipo de item (ex.: bebidas, perfumes, eletrônicos) — conferir a
  legislação vigente.

## Fase 4 — Aplicativo

* **Coleta no aparelho do usuário.** Como o site exige verificação humana, um servidor não
  consegue coletar sozinho. No app, as páginas teriam de ser carregadas no próprio
  celular/computador do turista (que resolve a verificação), ou o app usaria só a base já
  coletada. Decidir a arquitetura nesta fase.

* Lista suspensa de autocompletar usando `catalogo.sugerir_modelos()` (já pronta e testada).
* Telas de lista de compras, resultado (itens, lojas, roteiro, gasto, situação da cota).
* Exibição em R$ via `cotacao.obter_cotacao()` / `usd_para_brl()`.

## Melhorias da base de dados (podem entrar antes da Fase 2)

* Conferir o parser contra páginas reais (`python -m lesteshop.data.salvar_fixtures
  "playstation 5 pro"`) — as fixtures atuais foram escritas à mão porque o ambiente de
  desenvolvimento não tinha acesso ao site.
* Verificar se as ofertas da página de modelo são paginadas ou carregadas por JavaScript;
  hoje só lemos o HTML inicial.
* Popular `categoria` no catálogo (o sitemap não informa).
* Agrupar lojas do mesmo grupo (mesmo WhatsApp/razão social), se for desejado.
* O GitHub Actions não passa pela verificação anti-robô do site (confirmado: 403 com
  `cf-mitigated: challenge`). Enquanto for assim, atualizar o catálogo localmente com
  `python -m lesteshop.data.catalogo atualizar --navegador`, ou desativar o agendamento.
* Pedir autorização ao Compras Paraguai (e-mail explicando o projeto acadêmico) ou acesso a
  uma API.
