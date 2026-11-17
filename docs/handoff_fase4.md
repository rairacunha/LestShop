# Handoff para a Fase 4 — LesteShop

Documento autocontido para colar no início do chat da Fase 4. Repositório:
**`rairacunha/LestShop`** (branch `main`). Situação em 17/11/2026: Fases 1, 2 e 3
concluídas.

## 1. Contexto do projeto

O LesteShop é o projeto da disciplina de **Pesquisa Operacional II**. O turista informa o
que quer comprar em Ciudad del Este (Paraguai) e o app devolve onde comprar cada item, a
rota a pé a partir da Ponte da Amizade, o gasto total e a situação frente à cota de isenção
e às regras de bagagem da Receita Federal. O problema por trás é o **Traveling Purchaser
Problem** (Laporte, Riera-Ledesma e Salazar-González, 2003), com mochila (itens podem
ficar de fora), cota, imposto sobre o excedente e janelas de tempo.

### Regras de trabalho (obrigatórias)

* **Método cascata:** fazer **apenas a fase pedida**. O que for de outra fase vai para
  `docs/pendencias.md`, sem implementar.
* **Antes de implementar, apresentar a proposta** (formulação, opções e recomendação) e
  **esperar a aprovação** da dona do projeto, que valida as decisões com o professor.
* **Melhorias futuras NÃO são implementadas sem autorização explícita** (seção 7). O
  objetivo é manter o app o mais simples possível.
* Respostas e documentação em português. O código segue o estilo de `src/lesteshop/`.
* Dados inventados nunca são marcados como `real` (`tipo_dado = "sintetico"`).
* Todos os cálculos em **US$**; o R$ é só para exibição.
* Rodar `pytest` antes de cada commit (hoje: **245 passam, 4 pulados**, que dependem do
  site real).

## 2. Estrutura do repositório

```
LestShop/
├── .github/workflows/        atualização semanal do catálogo de modelos (GitHub Actions)
├── data/
│   ├── raw/                  base FICTÍCIA: 50 lojas, 73 produtos, 613 ofertas, nó 0, cotação
│   ├── instances/            inst_001…inst_100 (40 pequenas, 35 médias, 25 grandes)
│   ├── resultados/           experimentos da Fase 2 (resultados_fase2.csv, solucoes/, resumo)
│   │   └── fase3/            experimentos da Fase 3 (resultados_fase3.csv, solucoes/, resumo)
│   ├── regras_fiscais.csv    FASE 3: cota, alíquota e limites (versionada, fonte e vigência)
│   ├── categorias_fiscais.csv FASE 3: categoria/produto → categoria fiscal (editável à mão)
│   ├── catalogo_modelos.csv  catálogo de modelos (autocompletar)
│   └── lojas_complemento.csv coordenadas/prédios preenchidos à mão
├── scripts/gerar_base_ficticia.py   regenera a base fictícia (seed 2026, reprodutível)
├── src/lesteshop/
│   ├── data/                 FASE 1 — base de ofertas
│   │   ├── sources/          FonteDeOfertas: CSV, Compras Paraguai (navegador), API (futura)
│   │   ├── coletar.py        coleta de ofertas      catalogo.py  catálogo + sugerir_modelos()
│   │   ├── database.py       SQLite                 validator.py validação
│   │   ├── generator.py      instâncias sintéticas  resumo.py    resumo + exportação
│   │   └── cotacao.py        PTAX do Banco Central (exibição em R$)
│   ├── otimizacao/           FASE 2 — modelo de otimização
│   │   ├── instancia.py      leitura e pré-processamento de uma instância
│   │   ├── solucao.py        avaliação e descrever() (JSON com o resultado completo)
│   │   ├── modelo.py         modelo exato PuLP + CBC     heuristica.py  gulosa + busca local
│   │   ├── rota.py           agenda, 2-opt, polimento    distancias.py  tempos a pé
│   │   ├── resolver.py       comando: resolve uma instância
│   │   └── experimentos.py   100 instâncias + sensibilidade a r
│   └── fiscal/               FASE 3 — regras fiscais e de bagagem
│       ├── regras.py         tabela versionada      categorias.py mapeamento editável
│       ├── verificacao.py    limites e alertas      experimentos.py alertas nas 100 instâncias
├── tests/                    pytest
└── docs/
    ├── legislacao_bagagem.md   levantamento da legislação, fontes e decisões da Fase 3
    ├── modelo_matematico.md    formulação da Fase 2, dedução de λ, big-M, hipóteses
    ├── dicionario_de_dados.md  tabelas, instâncias, regras e colunas dos resultados
    ├── pendencias.md           o que ficou para outras fases e melhorias futuras
    ├── origem_dos_dados.md     fonte dos dados e limitações
    ├── testar_no_navegador.md  testar pelo GitHub Codespaces
    └── handoff_fase3.md, passagem_fase2.md  handoffs anteriores
```

```bash
pip install -e ".[dev]"
pytest
python -m lesteshop.otimizacao.resolver data/instances/inst_078_grande   # mostra também a parte fiscal
python -m lesteshop.otimizacao.experimentos --processos 3                # ~2,5 min, 250 rodadas
python -m lesteshop.fiscal.experimentos --processos 3                    # ~2 min, 100 rodadas
```

## 3. Fase 1 — base de dados (concluída)

Coleta do Compras Paraguai (`--navegador`: o usuário resolve a verificação anti-robô, que o
LesteShop não tenta contornar), validação, SQLite, catálogo de modelos com autocompletar
(`catalogo.sugerir_modelos()`), cotação PTAX (`cotacao.obter_cotacao()`, `usd_para_brl()`) e
gerador de instâncias. **A coleta real nunca foi executada no site**: o projeto usa a base
fictícia de `data/raw/`. O GitHub Actions é bloqueado pela verificação do site (403).

Instâncias: pequena = 5 lojas × 10 produtos, média = 15 × 40, grande = 40 × 70. Cada pasta
tem `lojas.csv`, `produtos.csv`, `ofertas.csv`, `pontos_partida.csv`, `lista_compras.csv`
(produto, quantidade, prioridade 1–5) e `metadata.json` (orçamento, custo mínimo da lista,
horários de chegada e saída, número real de lojas). Desde a Fase 3 o `metadata.json`
**não** tem cota nem alíquota.

## 4. Fase 2 — modelo de otimização (concluída)

`resolver(carregar_instancia(pasta), r=0.25)` devolve (solução final, solução da
heurística), e `descrever(solucao, inst)` devolve o dicionário (JSON) com itens, roteiro com
horários, gasto, imposto, situação da cota, bagagem, avisos e o bloco `fiscal`. Fluxo:
heurística → modelo exato (PuLP + CBC) com a heurística como *warm start* → polimento da
ordem de visita. O projeto fixa `pulp>=2.7,<4` (o PuLP 4 não traz o CBC).

Resultados (base fictícia, r = 0,25, cota de US$ 500 em todas as instâncias):

| tamanho | ótimo provado | gap máximo | tempo mediana / máximo | heurística = exato |
|---|---|---|---|---|
| pequena (40) | 40/40 | 0 | 0,02 s / 0,06 s | 40/40 |
| média (35) | 34/35 | 3,9% (`inst_075_media`, limite de 60 s mantido) | 0,08 s / 60 s | 35/35 |
| grande (25) | 25/25 | 0 | 3,0 s / 22,6 s | 24/25 (a outra a 0,002%) |

69 instâncias deixam algum item de fora, 38 pagam imposto (US$ 222 em média quando pagam),
prioridade atendida média de 90,6%. A prioridade atendida não muda com r (0; 0,25; 1).
Nenhuma solução inviável.

## 5. Fase 3 — regras fiscais e de bagagem (concluída)

* **Levantamento** em `docs/legislacao_bagagem.md`, com a norma e o texto vigente de cada
  regra (Portaria MF 440/2010, IN RFB 1.059/2010, IN RFB 1.385/2013, Portaria MF 307/2014,
  IN RFB 2.075/2022 e o Guia do Viajante do gov.br).
* **Tabela `data/regras_fiscais.csv`**: única fonte da cota (US$ 500, via terrestre,
  Portaria ME 601/2019) e da alíquota (50%, RTE); limites de bebidas (12 L), cigarros
  (10 maços), charutos (25), fumo (250 g), bens < US$ 5 (20 unidades, 10 idênticas) e
  demais bens (10 unidades, 3 idênticas). Para cada regra vale a linha mais recente já em
  vigor (hoje a data de referência é a data do dia).
* **Modelo sem mudanças.** Os limites são verificados depois de otimizar e só geram
  alertas. O bloco `fiscal` de `descrever()` traz o uso de cada limite, os alertas, o
  **imposto sem cota** (0,5·G) quando a norma tira a isenção, se a **declaração (e-DBV)**
  é necessária e a **premissa** da cota integral.
* **Resultado:** 4 das 100 cestas ótimas passam do limite de 10 unidades (todas grandes);
  nenhuma passa de 12 L de bebida; 38 precisam de declaração por passar da cota.

## 6. Decisões já aprovadas (não rediscutir sem motivo)

### Dados e modelo
* Base fictícia nos experimentos; número real de lojas do `metadata.json`; lojas com
  coordenada pendente ficam de fora, com aviso; oferta repetida na mesma loja vale a de
  menor preço; cada item é comprado inteiro numa única loja; horários vazios: 07:00–16:00,
  permanência de 20 min.
* Objetivo único: max Σ v_k·y_k − λ·(G + α·E + r·Σ t_ij·x_ij), v_k = prioridade 1–5,
  λ = 1/(B + r·T_max + 1), **r = US$ 0,25/min**. Orçamento opcional (se não informado,
  B = cota); lista que não cabe não torna o problema inviável.
* Tempos: haversine × 1,3 ÷ 75 m/min; 1 min no mesmo prédio; janelas completas; big-M por
  instância. PuLP + CBC, 60 s (pequenas e médias) e 300 s (grandes), mantidos; a solução
  final nunca é pior que a da heurística. Bagagem (peso/volume) opcional e desligada.

### Regras fiscais (Fase 3)
* Cada rota é uma **viagem nova, com a cota integral** (premissa: a cota não foi usada no
  mês anterior à entrada); o app não guarda histórico de compras.
* Limites quantitativos **só como alerta**; quantidade > 1 = oferta em lote (y_k binário).
* Ultrapassar os limites de unidades: o alerta mostra também o imposto sem cota.
* Excesso de bebidas: **só alerta** (vai para o regime comum), sem recomendar que o
  turista deixe de comprar: é um risco que ele tem o direito de assumir.
* **Destinação comercial fora do escopo**: quem compra para revender importa pelo
  procedimento do comércio, com CNPJ.
* Bens de uso pessoal, proibidos ou restritos: fora do escopo.

## 7. Melhorias futuras — NÃO implementar sem autorização

> **Regra explícita:** nenhum item abaixo deve ser implementado, nem servir de motivo para
> alterar código, modelo ou parâmetros, sem autorização da dona do projeto. Ideias novas
> só são registradas em `docs/pendencias.md`, na seção "Melhorias futuras".

1. Objetivo lexicográfico em 3 níveis.
2. Barra "prefiro economizar ↔ prefiro andar menos" no app, ajustando r.
3. "Favorito" (estrela) no lugar da prioridade 1–5.
4. Desempate pela economia em relação ao Brasil (`produtos.desconto_brasil_pct`).
5. Calibrar o fator de circuidade com rotas a pé reais.
6. Velocidade menor nas subidas (Tobler, 1993).
7. Reotimização dinâmica da rota durante o passeio (Pillac et al., 2013).
8. Permanência por loja = tempo fixo + tempo por item.
9. Heurística como Iterated Local Search.

Também em `pendencias.md` (igualmente sem autorização): formulação mais forte para a
`inst_075_media`, PuLP 4, rotas a pé reais (OSRM/Google), fila da aduana, estoque, dados
reais nos experimentos, data da viagem como data de referência das regras e cota de loja
franca de fronteira (não se aplica às lojas de Ciudad del Este).

## 8. Proposta de escopo da Fase 4 — aplicativo

**É apenas uma proposta**, para validar com o professor **antes** de implementar. O
primeiro passo da Fase 4 é apresentar as opções e esperar a aprovação.

### 8.1 O que já está pronto para o app usar
* `catalogo.sugerir_modelos(texto)` para o autocompletar;
* `carregar_instancia()` + `resolver()` + `descrever()`, que devolve o resultado inteiro em
  JSON (itens, roteiro com horários, gasto, imposto, cota, bagagem, alertas fiscais);
* `cotacao.obter_cotacao()` e `usd_para_brl()` para mostrar em R$;
* a base fictícia completa em `data/raw/` (e o SQLite de `database.py`).

O que **falta**: montar uma instância a partir do que o turista digita (lista, quantidades,
prioridades, horários e orçamento) e da base, em vez de ler uma pasta de `data/instances/`.

### 8.2 Decisões a tomar (com a recomendação de cada uma)

1. **Plataforma.**
   * (a) **App web em Python com Streamlit**, rodando no computador ou no GitHub
     Codespaces. Reaproveita todo o código, sem servidor separado. **Recomendado** para a
     disciplina.
   * (b) API (FastAPI) + página web ou PWA para celular. Mais trabalho e mais uma
     linguagem (JavaScript).
   * (c) App nativo de celular. Fora do alcance do projeto.
2. **Origem dos dados (arquitetura de coleta).**
   * (a) **O app usa só a base já coletada** (CSV/SQLite), atualizada à parte pela dona
     do projeto com `coletar --navegador`. Hoje seria a base fictícia, sempre marcada como
     tal na tela. **Recomendado.**
   * (b) Coleta no aparelho do turista (as páginas do Compras Paraguai carregadas no
     celular dele, que resolve a verificação). Exige app nativo ou extensão; fica para
     depois.
   * Em paralelo, pedir autorização ao Compras Paraguai antes de qualquer coleta real.
3. **Telas mínimas.**
   * Lista de compras: busca com autocompletar, quantidade e prioridade 1–5 por item.
   * Dados da viagem: horário de chegada e de saída no lado paraguaio, orçamento opcional
     e, se aprovado, a data da viagem.
   * Resultado: itens com loja e preço, roteiro na ordem com horários, itens deixados de
     fora, gasto, imposto, custo total, bloco fiscal (limites, alertas, imposto sem cota,
     declaração e premissa), valores em US$ e R$.
4. **Mapa do roteiro.** Mostrar as lojas e a ordem num mapa (ex.: `pydeck` ou `folium`)
   ou só a lista. Recomendado: só a lista na primeira versão; o mapa como opção, se o
   professor quiser.
5. **Data da viagem.** Usar a data informada como data de referência das regras fiscais
   (hoje é a data do dia). Recomendado: sim, é uma mudança pequena e o campo já existe nas
   regras.
6. **r no app.** Fica fixo em US$ 0,25/min (a barra para ajustar r é melhoria futura).

### 8.3 Fora da Fase 4 (proposta)
* Coleta no aparelho do usuário e coleta automática no servidor.
* Contas de usuário, histórico de compras e cota residual entre viagens.
* Qualquer item da seção 7.

### 8.4 Perguntas para o professor
1. A plataforma Streamlit (web, em Python) atende à disciplina, ou é preciso um app de
   celular?
2. Basta o app usar a base já coletada (hoje fictícia), deixando a coleta no aparelho para
   depois?
3. O roteiro precisa aparecer num mapa, ou a lista com horários é suficiente?
4. A data da viagem informada pelo turista deve escolher a versão das regras fiscais?
