# Pendências para as próximas fases

Itens percebidos durante as Fases 1 e 2 que **não** foram implementados por pertencerem a
outras fases do modelo cascata.

> **Regra:** nada desta lista é implementado sem autorização explícita da dona do projeto.
> O objetivo é manter o app o mais simples possível.

## Fase 2 — Modelo de otimização (TPP) — concluída

Implementada em `src/lesteshop/otimizacao/`, formulação em
[`modelo_matematico.md`](modelo_matematico.md), resultados em
`data/resultados/resumo_experimentos.md`. Decisões aprovadas e implementadas:

* uma única resolução: max Σ v_k·y_k − λ·(G + α·E + r·Σ t_ij·x_ij), com
  λ = 1/(B + r·T_max + 1) e r = US$ 0,25/min (padrão);
* orçamento opcional (B = cota se não informado), limite rígido de preço + imposto;
  itens podem ficar de fora (mochila); prioridade 1–5 = v_k;
* imposto de 50% sobre o excedente da cota, sempre reexibido como α·max(0, G − c);
* tempos: haversine × 1,3 ÷ 75 m/min (média, sem considerar o relevo), 1 min no mesmo
  prédio (exceto "Rua"); permanência fixa por loja, sem depender da quantidade de itens;
* janelas de tempo completas (turista + lojas, com espera), padrões 07:00–16:00 e
  20 min; big-M por instância M = max(fecha) + max(s) + max(t) − min(abre);
* PuLP + CBC com a heurística como solução inicial; 60 s (pequenas/médias) e 300 s
  (grandes), **mantidos** mesmo quando uma instância para no limite: o gap é reportado
  (`status`, `gap` e `tempo_exato_s` em `resultados_fase2.csv`; distribuição dos gaps no
  resumo); polimento da ordem de visita (exato até 10 lojas, senão 2-opt);
* bagagem (peso/volume) opcional e desligada por padrão; totais sempre exibidos;
* lojas com coordenada pendente excluídas com aviso dos itens afetados; oferta
  repetida na mesma loja usa o menor preço; quantidade comprada toda numa loja.

### Ficou para depois (percebido na Fase 2)

* **Formulação mais forte para casos difíceis** (não implementar; o limite de 60 s foi
  mantido e o gap é reportado). Em 1 das 100 instâncias
  (`inst_075_media`) o CBC para no limite de 60 s com gap de ~3,9% (a heurística acha
  a mesma incumbente, mas o limitante não descarta 1 ponto a mais de prioridade). Com
  600 s o CBC prova o ótimo em ~390 s (a incumbente já era ótima). Um big-M por arco
  não ajudou (a folga vem da relaxação da mochila). Opções: cortes
  de cobertura no orçamento, restrições de subrota mais fortes (GSEC) ou branch-and-cut
  como em Laporte et al. (2003).
* **PuLP 4.** A versão 4 não traz o CBC embutido e vai remover `PULP_CBC_CMD`. O projeto
  fixa `pulp>=2.7,<4`; migrar para `COIN_CMD` + `pip install pulp[cbc]` quando for
  atualizar.
* **Rotas a pé reais** (OSRM, Google Maps) no lugar de haversine × 1,3, quando houver
  coordenadas reais de lojas.
* **Fila da aduana / travessia da Ponte.** H⁰ e H¹ são horários no lado paraguaio; a
  espera não é modelada.
* **Estoque** (hoje cada item é comprado inteiro numa única loja). Permanência por item:
  ver "Melhorias futuras".
* **Rodar os experimentos com dados reais** quando a coleta do Compras Paraguai
  for executada (a Fase 2 usou só a base fictícia).

## Fase 3 — Regras fiscais

* Levantamento da legislação concluído em
  [`legislacao_bagagem.md`](legislacao_bagagem.md); decisões de 16/11/2026 na seção 11.
* Fica **fora** da Fase 3 (decidido): histórico de compras e cota residual entre viagens
  (cada rota é uma viagem nova, com a cota integral), limites como restrição rígida,
  quantidade inteira (y_k continua binário), bens de uso pessoal, proibidos ou restritos,
  e **destinação comercial** (o comércio importa com CNPJ, pelo regime comum).

### Implementado (7.2)

Módulo `src/lesteshop/fiscal/`, tabela versionada `data/regras_fiscais.csv` (única fonte
da cota), mapeamento editável `data/categorias_fiscais.csv`, bloco `fiscal` em
`descrever()` (situação de cada limite, alertas, imposto sem cota, declaração), testes em
`tests/test_fiscal.py` e experimentos em `data/resultados/fase3/`. O modelo de otimização
não mudou.

### Fechamento da Fase 3 (aprovado em 17/11/2026)

* **Alíquota na tabela de regras.** A alíquota de 50% do RTE passou para
  `data/regras_fiscais.csv` (regra `aliquota_rte`, Portaria MF 440/2010, art. 12). O campo
  `aliquota_excedente` saiu dos `metadata.json`; se aparecer num arquivo antigo, é
  ignorado com aviso. A tabela agora é a única fonte da cota e da alíquota.
* **Experimentos da Fase 2 refeitos** com a cota integral de US$ 500 em todas as
  instâncias (`resultados_fase2.csv` e `resumo_experimentos.md` atualizados). Das 250
  rodadas, 79 mudaram, todas de instâncias que antes tinham cota de 300 ou 150; nenhuma
  das que já tinham cota de 500 mudou. Com r = 0,25: itens deixados de fora em 69
  instâncias (antes 74), imposto em 38 (antes 50; média de US$ 222,14 quando paga, antes
  US$ 209,58), prioridade atendida média de 90,6% (antes 89,5%). O solver não mudou de
  comportamento: 99 ótimos provados, `inst_075_media` no limite com gap de 3,91%,
  heurística = exato em 99, nenhuma solução inviável. A conferência da Fase 3 agora dá
  100 de 100 instâncias com a mesma solução nas duas rodadas.

### Ficou para depois (percebido na Fase 3; não implementar sem autorização)

* **Data de referência das regras.** Fica a data do dia (decidido em 18/11/2026: o app
  não pergunta a data da viagem).
* **Cota adicional de loja franca de fronteira (Foz do Iguaçu).** Não se aplica às lojas
  de Ciudad del Este; só faria sentido se o app passasse a incluir lojas do lado brasileiro.

## Fase 4 — Aplicativo

Escopo decidido em 18/11/2026 (detalhes em [`handoff_fase4.md`](handoff_fase4.md),
seção 8): Streamlit; coleta real no computador da dona do projeto, com horário comercial
padrão para as lojas e coordenadas à mão; base fictícia identificada enquanto não houver
a real; data da viagem não é perguntada; mapa e alteração manual ficam para melhorias.

* Exibir na tela o bloco `fiscal` (uso de cada limite, alertas, imposto sem cota,
  declaração e-DBV) e o texto da premissa da cota integral.

* **Coleta no aparelho do usuário.** Como o site exige verificação humana, um servidor não
  consegue coletar sozinho. No app, as páginas teriam de ser carregadas no próprio
  celular/computador do turista (que resolve a verificação), ou o app usaria só a base já
  coletada. Decidir a arquitetura nesta fase.

* Lista suspensa de autocompletar usando `catalogo.sugerir_modelos()` (já pronta e testada).
* Telas de lista de compras, resultado (itens, lojas, roteiro, gasto, situação da cota).
* Exibição em R$ via `cotacao.obter_cotacao()` / `usd_para_brl()`.
* Tela de resultado a partir de `otimizacao.solucao.descrever()` (JSON pronto com itens,
  roteiro, gasto, imposto, situação da cota, bagagem e avisos).

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

Registradas para não se perderem. **Nenhuma delas deve ser implementada sem autorização
explícita** (código, modelo e parâmetros continuam como aprovados na Fase 2).

* **Calibrar o fator de circuidade** (hoje 1,3) comparando a distância em linha reta com
  a rota a pé real (Google Maps) numa amostra de pares de lojas.
* **Velocidade a pé menor nas subidas.** Ciudad del Este tem muitas ladeiras; a
  velocidade poderia depender da declividade do trecho, pela função de caminhada de
  Tobler (TOBLER, W. *Three presentations on geographical analysis and modeling*.
  NCGIA Technical Report 93-1, 1993). Hoje 75 m/min é uma média única.
* **Reotimização dinâmica da rota** a partir da localização e do horário atuais do
  usuário, durante o passeio (PILLAC, V. et al. A review of dynamic vehicle routing
  problems. *European Journal of Operational Research*, v. 225, n. 1, p. 1–11, 2013).
* **Mapa do roteiro com alteração manual** (em espera desde 18/11/2026): mostrar as lojas
  num mapa e deixar o turista mudar a ordem das lojas ou a loja de cada item, com
  recálculo de horários, preço, imposto e alertas e um botão "voltar à sugestão ótima".
  A alteração só reavalia a rota escolhida; o modelo não muda.
* **Permanência por loja = tempo fixo + tempo por item comprado** (hoje é só o tempo
  fixo da loja).
* **Heurística como Iterated Local Search (ILS):** construção gulosa + 2-opt +
  perturbação + critério de aceitação, conforme a aula de ILS (hoje é construção gulosa
  + busca local até não haver melhora, sem perturbação).

* **Objetivo lexicográfico em 3 níveis.** 1º maximizar a prioridade; 2º, com a
  prioridade fixada, minimizar gasto + imposto; 3º, com o gasto fixado (com tolerância
  ε em US$), minimizar o tempo andando. Proposto na Fase 2 e recusado por ora pela
  complexidade (três resoluções por instância). Hoje o ponderado com λ já garante o
  1º nível; o 2º e o 3º são trocados à taxa r.
* **Barra "prefiro economizar ↔ prefiro andar menos"** no app, ajustando o valor do
  minuto r (ex.: 0 a US$ 1/min). A análise de sensibilidade da Fase 2 (r = 0; 0,25; 1)
  mostra o efeito esperado.

* **"Favorito" no lugar da prioridade 1 a 5.** O usuário marcaria itens com estrela
  (sim/não), e o modelo usaria pesos lexicográficos: primeiro maximizar os favoritos
  comprados, depois o número de itens comuns. Avaliado com o professor e adiado por
  aumentar a complexidade do modelo.
* **Desempate pela economia em relação ao Brasil.** Entre itens de mesma prioridade,
  preferir o de maior economia em US$: preço × desconto ÷ (1 − desconto), usando
  `produtos.desconto_brasil_pct`. Ex.: preço US$ 700 com desconto 0,28 → economia ≈ US$ 272.
