# Pendências para as próximas fases

Itens percebidos durante a Fase 1 que **não** foram implementados por pertencerem a
outras fases do modelo cascata.

## Fase 2 — Modelo de otimização (TPP)

### Decisões já tomadas (validadas com o professor em 28/10/2026)

* **Orçamento é OPCIONAL.** Se o usuário informar, é limite rígido de gasto total
  (preço + imposto). Se não informar, o teto é a própria cota (US$ 500).
* **Lista que não cabe no orçamento não torna o problema inviável:** o modelo pode deixar
  itens de fora (estrutura de mochila).
* **Prioridade 1 a 5 é o valor v_i de cada item** na função objetivo da mochila,
  max Σ v_i · x_i. A coluna `prioridade` das instâncias fica como está.
* **Imposto em 64 das 100 instâncias é intencional**, para testar cenários dentro e fora da cota.
* **Instâncias com menos lojas que o nominal são aceitas** (consequência de "loja sem oferta
  é descartada"). Nos experimentos, usar sempre o número real de lojas do `metadata.json`.
* **Tamanho grande = 40 lojas e 70 produtos**, sem variantes artificiais. O tamanho do
  problema é dado pela lista de compras e pelo número de lojas, não pelo catálogo.

### Dados já preparados

* `data/instances/inst_001…inst_100`: lista de compras com prioridade, cota disponível,
  orçamento e janela de tempo, guardados e validados na Fase 1, sem uso ainda. Em 52
  instâncias o orçamento é menor que o custo mínimo da lista: pela decisão acima, o modelo
  escolhe quais itens deixar de fora.
* `produtos.desconto_brasil_pct`: desconto anunciado pelo Compras Paraguai em relação ao
  Brasil (vazio na base fictícia).

### A fazer

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

## Melhorias futuras (depois que o app estiver funcionando)

Registradas para não se perderem; **não implementar antes disso**.

* **"Favorito" no lugar da prioridade 1 a 5.** O usuário marcaria itens com estrela
  (sim/não), e o modelo usaria pesos lexicográficos: primeiro maximizar os favoritos
  comprados, depois o número de itens comuns. Avaliado com o professor e adiado por
  aumentar a complexidade do modelo.
* **Desempate pela economia em relação ao Brasil.** Entre itens de mesma prioridade,
  preferir o de maior economia em US$: preço × desconto ÷ (1 − desconto), usando
  `produtos.desconto_brasil_pct`. Ex.: preço US$ 700 com desconto 0,28 → economia ≈ US$ 272.
