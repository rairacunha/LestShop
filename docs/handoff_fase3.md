# Handoff para a Fase 3 — LesteShop

Documento autocontido para colar no início do chat da Fase 3. Repositório:
**`rairacunha/LestShop`** (branch `main`). Situação em 09/11/2026: Fases 1 e 2
concluídas.

## 1. Contexto do projeto

O LesteShop é o projeto da disciplina de **Pesquisa Operacional II**. O turista informa o
que quer comprar em Ciudad del Este (Paraguai) e o app devolve onde comprar cada item, a
rota a pé a partir da Ponte da Amizade, o gasto total e a situação frente à cota de isenção
da Receita Federal. O problema por trás é o **Traveling Purchaser Problem** (Laporte,
Riera-Ledesma e Salazar-González, 2003), com mochila (itens podem ficar de fora), cota,
imposto sobre o excedente e janelas de tempo.

### Regras de trabalho (obrigatórias)

* **Método cascata:** fazer **apenas a fase pedida**. O que for de outra fase vai para
  `docs/pendencias.md`, sem implementar.
* **Antes de implementar, apresentar a proposta** (formulação, opções e recomendação) e
  **esperar a aprovação** da dona do projeto, que valida as decisões com o professor.
* **Melhorias futuras NÃO são implementadas sem autorização explícita** (seção 6). O
  objetivo é manter o app o mais simples possível.
* Respostas e documentação em português. O código segue o estilo de `src/lesteshop/`.
* Dados inventados nunca são marcados como `real` (`tipo_dado = "sintetico"`).
* Todos os cálculos em **US$**; o R$ é só para exibição.
* Commits e push no `main`. Rodar `pytest` antes de cada commit.

## 2. Estrutura do repositório

```
LestShop/
├── .github/workflows/        atualização semanal do catálogo de modelos (GitHub Actions)
├── data/
│   ├── raw/                  base FICTÍCIA: 50 lojas, 73 produtos, 613 ofertas, nó 0, cotação
│   ├── instances/            inst_001…inst_100 (40 pequenas, 35 médias, 25 grandes)
│   ├── resultados/           experimentos da Fase 2: resultados_fase2.csv, solucoes/, resumo
│   ├── catalogo_modelos.csv  catálogo de modelos (autocompletar)
│   └── lojas_complemento.csv coordenadas/prédios preenchidos à mão
├── src/lesteshop/
│   ├── data/                 FASE 1 — base de ofertas
│   │   ├── sources/          FonteDeOfertas: CSV, Compras Paraguai (navegador), API (futura)
│   │   ├── coletar.py        coleta de ofertas      catalogo.py  catálogo + sugerir_modelos()
│   │   ├── database.py       SQLite                 validator.py validação
│   │   ├── generator.py      instâncias sintéticas  resumo.py    resumo + exportação
│   │   └── cotacao.py        PTAX do Banco Central (exibição em R$)
│   └── otimizacao/           FASE 2 — modelo de otimização
│       ├── config.py         parâmetros padrão (r, velocidade, circuidade, limites)
│       ├── distancias.py     matriz de tempos a pé
│       ├── instancia.py      leitura e pré-processamento de uma instância
│       ├── rota.py           agenda com janelas, 2-opt, polimento da ordem de visita
│       ├── solucao.py        avaliação (gasto, imposto, objetivo) e descrever() (JSON)
│       ├── modelo.py         modelo exato PuLP + CBC
│       ├── heuristica.py     construção gulosa + busca local
│       ├── resolver.py       comando: resolve uma instância
│       └── experimentos.py   roda as 100 instâncias + sensibilidade a r
├── tests/                    pytest (208 passam, 4 pulados: dependem do site real)
└── docs/
    ├── dicionario_de_dados.md  tabelas, instâncias e colunas dos resultados
    ├── modelo_matematico.md    formulação da Fase 2, dedução de λ, big-M, hipóteses
    ├── pendencias.md           o que ficou para outras fases e melhorias futuras
    ├── origem_dos_dados.md     fonte dos dados e limitações
    ├── passagem_fase2.md       handoff anterior (Fase 1 → 2)
    └── handoff_fase3.md        este documento
```

## 3. Fase 1 — base de dados (concluída)

**Entregue:** coleta do Compras Paraguai (`--navegador`; o usuário resolve a verificação
anti-robô, que o LesteShop não tenta contornar), validação, SQLite, catálogo de modelos
com autocompletar, cotação PTAX e gerador de instâncias. A coleta real **nunca foi
executada no site**; o projeto usa a **base fictícia** de `data/raw/` (seed 2026,
reprodutível com `python scripts/gerar_base_ficticia.py`).

**Instâncias:** pequena = 5 lojas × 10 produtos, média = 15 × 40, grande = 40 × 70. Cada
pasta tem `lojas.csv`, `produtos.csv`, `ofertas.csv`, `pontos_partida.csv`,
`lista_compras.csv` (produto, quantidade, prioridade 1–5) e `metadata.json` (cota
disponível 500/300/150, alíquota 0,5, orçamento, custo mínimo da lista, horário de chegada
e de saída, número real de lojas). Em 64 instâncias a lista excede a cota, e em 52 o
orçamento é menor que o custo mínimo da lista (ambos intencionais).

```bash
pip install -e ".[dev]"
pytest
python -m lesteshop.data.resumo
python -m lesteshop.data.generator --size media --seed 42
```

## 4. Fase 2 — modelo de otimização (concluída)

**Entregue:** pacote `src/lesteshop/otimizacao/`, documentação em
`docs/modelo_matematico.md`, 22 testes em `tests/test_otimizacao.py` e experimentos em
`data/resultados/`.

```bash
python -m lesteshop.otimizacao.resolver data/instances/inst_001_pequena
python -m lesteshop.otimizacao.resolver data/instances/inst_002_pequena --sem-orcamento
python -m lesteshop.otimizacao.resolver data/instances/inst_010_pequena --peso-max 10 --json saida.json
python -m lesteshop.otimizacao.experimentos --processos 3      # ~2,5 min para 250 rodadas
python -m lesteshop.otimizacao.experimentos --so-resumo
```

Em Python: `resolver(carregar_instancia(pasta), r=0.25)` devolve (solução final, solução
da heurística), e `descrever(solucao, inst)` devolve um dicionário com itens, roteiro,
gasto, imposto, situação da cota, bagagem e avisos.

Fluxo: heurística → modelo exato (PuLP + CBC) com a heurística como *warm start* →
polimento da ordem de visita. O solver é o CBC embutido no PuLP; por isso o projeto fixa
`pulp>=2.7,<4` (o PuLP 4 não traz o CBC).

### Principais resultados (base fictícia, r = 0,25)

| tamanho | ótimo provado | gap médio / máximo | tempo mediana / máximo |
|---|---|---|---|
| pequena (40) | 40/40 | 0 / 0 | 0,02 s / ~10 s (atraso pontual do ambiente) |
| média (35) | 34/35 | 0,11% / 3,9% | 0,10 s / 60 s (limite) |
| grande (25) | 25/25 | 0 / 0 | 2,9 s / 22 s |

* Só a `inst_075_media` atinge o limite de 60 s (gap de 3,9%, nas três rodadas de r). Com
  600 s o CBC prova o ótimo em ~390 s, e a incumbente já era a da heurística. **Decisão:
  manter os 60 s e reportar o gap.**
* Heurística × exato: mesmo objetivo em 99 de 100 instâncias. A exceção (`inst_086_grande`)
  fica a 0,002%. A heurística leva no máximo 0,33 s.
* 74 instâncias deixam algum item de fora (mochila) e 50 pagam imposto (~US$ 200 em média).
* O polimento quase não muda nada (o exato já devolve a melhor ordem); encurtou uma rota da
  heurística em 1,2 min.
* Sensibilidade (pequenas e médias): a prioridade atendida **não muda** com r. De r = 0 a
  r = 1, as médias andam de 55,7 a 46,3 min e pagam de US$ 703,67 a 706,57 em média.
* Nenhuma solução inviável na verificação independente.

## 5. Decisões já aprovadas (não rediscutir sem motivo)

### Dados
* Base fictícia para os experimentos; usar sempre o **número real de lojas** do
  `metadata.json` (10 instâncias têm menos que o nominal).
* Tamanho grande = 40 lojas × 70 produtos, sem variantes artificiais.
* Lojas com `coordenada_pendente = true` ficam de fora, com aviso listando os itens da
  lista que perderam essa opção de compra.
* Oferta repetida da mesma loja para o mesmo produto: vale a de menor preço.
* Cada item é comprado inteiro (toda a quantidade) numa única loja.
* Horários vazios: abre 07:00, fecha 16:00, permanência de 20 min.

### Modelo e função objetivo
* TPP com mochila: max Σ v_k·y_k − λ·(G + α·E + r·Σ t_ij·x_ij), **uma única resolução**
  (o lexicográfico foi recusado pelo professor por complexidade).
* **v_k = prioridade 1–5** do item.
* **λ = 1 / (B + r·T_max + 1)**, com T_max = H¹ − H⁰ em minutos. Garante λ·(gasto + tempo)
  < 1: a prioridade sempre domina, e custo e tempo só decidem entre soluções de mesma
  prioridade. Dedução em `modelo_matematico.md`, seção 4.2.
* **r = US$ 0,25/min**: o turista aceita pagar até US$ 0,25 a mais para andar 1 minuto a menos.
* **Orçamento opcional**: se informado, é limite rígido de preço + imposto; se não, B = cota.
  Lista que não cabe no orçamento não torna o problema inviável (itens ficam de fora).

### Imposto
* Cota de isenção: US$ 500 por via terrestre a cada 30 dias. A cota **disponível** vem no
  `metadata.json` (500, 300 ou 150).
* **50% sobre o excedente**: E ≥ G − c, E ≥ 0 (linear, sem binária). O imposto exibido é
  sempre recalculado depois de resolver: α·max(0, G − c).

### Tempos e janelas
* t_ij = haversine × **1,3** (circuidade, Ballou, Rahardja e Sakai, 2002) ÷ **75 m/min**
  (média, sem considerar o relevo); **1 min** entre lojas do mesmo prédio ("Rua (loja de
  rua)" não agrupa); mínimo de 1 min entre nós distintos.
* Janela completa: chegada H⁰ e saída H¹ do turista **no lado paraguaio** (a fila da
  aduana não é modelada), horário de cada loja (com espera permitida) e **permanência fixa
  por loja**, sem depender da quantidade de itens.
* Big-M por instância: **M = max(fecha) + max(s_i) + max(t_ij) − min(abre)**, com as
  janelas recortadas pela do turista; o valor é registrado no resultado.

### Solver
* **PuLP + CBC**, 1 thread, heurística como solução inicial e como comparação.
* Limite de **60 s** nas pequenas e médias e **300 s** nas grandes, **mantido** mesmo quando
  não fecha; status, gap e tempo vão para `resultados_fase2.csv`, e o resumo mostra a
  distribuição dos gaps.
* Polimento: mantém lojas e compras e reotimiza só a ordem (exato via PuLP até 10 lojas,
  senão 2-opt); só aceita se for viável e reduzir o tempo andando. Registra o tempo andando
  antes e depois.
* A solução final nunca é pior que a da heurística.
* Bagagem (peso/volume): restrição **opcional e desligada** por padrão; os totais são sempre
  exibidos.

## 6. Melhorias futuras — NÃO implementar sem autorização

> **Regra explícita:** nenhum item abaixo deve ser implementado, nem servir de motivo para
> alterar código, modelo ou parâmetros, sem autorização da dona do projeto. Quando surgir
> uma ideia nova, ela só é registrada em `docs/pendencias.md`, na seção "Melhorias futuras".

1. Objetivo lexicográfico em 3 níveis (prioridade → gasto + imposto → tempo andando).
2. Barra "prefiro economizar ↔ prefiro andar menos" no app, ajustando r.
3. "Favorito" (estrela) no lugar da prioridade 1–5, com pesos lexicográficos.
4. Desempate pela economia em relação ao Brasil (`produtos.desconto_brasil_pct`).
5. Calibrar o fator de circuidade comparando linha reta × rota a pé real (Google Maps) numa
   amostra de pares de lojas.
6. Velocidade a pé menor nas subidas (função de caminhada de Tobler, 1993).
7. Reotimização dinâmica da rota a partir da localização e do horário atuais do usuário
   (Pillac et al., EJOR, 2013).
8. Permanência por loja = tempo fixo + tempo por item comprado.
9. Heurística como Iterated Local Search (construção gulosa + 2-opt + perturbação +
   aceitação), conforme a aula de ILS.

Também registrados em `pendencias.md` (igualmente sem autorização para implementar): uma
formulação mais forte para casos como a `inst_075_media`, a migração para o PuLP 4, rotas a
pé reais (OSRM/Google), a fila da aduana, estoque e rodar os experimentos com dados reais.

## 7. Proposta de escopo da Fase 3 — regras fiscais e de bagagem

**É apenas uma proposta**, para validar com o professor **antes** de implementar. Na Fase 3,
como nas anteriores, o primeiro passo é apresentar a formulação e as opções e esperar a
aprovação.

### 7.1 Levantamento da legislação (primeira entrega, só documento)

Montar `docs/legislacao_bagagem.md` com a regra vigente e a fonte oficial de cada item
(Receita Federal: Instrução Normativa de bagagem, hoje a IN RFB nº 1.059/2010 e alterações,
e as páginas "Viajantes" do gov.br). Pontos a **conferir** (não tomar como certos sem a fonte):

* valor da cota por **via terrestre** (o projeto usa US$ 500) e a periodicidade (a cada 30
  dias, pessoal e intransferível);
* **limites quantitativos** dentro da cota: bebidas alcoólicas (litros), cigarros, charutos
  e fumo, e o limite de unidades para bens de pequeno valor e para itens idênticos;
* o que **não entra na cota** (bens de uso ou consumo pessoal, livros e periódicos etc.) e
  quais produtos são **proibidos ou restritos** (por exemplo, itens que exigem anuência da
  Anvisa ou de outros órgãos);
* o **regime de tributação especial** (50% sobre o excedente) e a **presunção de destinação
  comercial** (quantidade ou frequência que descaracteriza a bagagem);
* a **declaração** obrigatória quando a cota é excedida (e-DBV) e a eventual cota adicional
  de *free shop* de fronteira terrestre, se aplicável.

### 7.2 Proposta de implementação (depois da aprovação)

* **Tabela de regras** versionada (`data/regras_fiscais.csv`), com tipo de limite (valor,
  quantidade, litros), categoria, limite, fonte e data de vigência, carregada por um módulo
  novo `src/lesteshop/fiscal/`.
* **Mapeamento produto → categoria fiscal** (a partir de `produtos.categoria`), com um
  arquivo de correspondência editável à mão.
* **Limites por tipo e quantidade como restrições lineares** do modelo da Fase 2:
  Σ_{k ∈ categoria} q_k·y_k ≤ L_categoria. Mantém a mochila, sem mudar a função objetivo, λ
  nem r.
* **Itens proibidos ou fora da cota:** excluídos do modelo, com aviso, ou somados fora de G
  (a forma depende do levantamento).
* **Cota disponível calculada** a partir de um histórico simples de compras dos últimos 30
  dias (hoje vem pronta no `metadata.json`), mantendo a opção de informá-la diretamente.
* **Saídas novas em `descrever()`:** situação por categoria (quanto do limite foi usado),
  alerta de destinação comercial e indicação de que a declaração é necessária.
* **Testes** com casos montados à mão para cada regra, e uma nova rodada dos experimentos
  para medir o efeito dos limites.

### 7.3 Fica fora da Fase 3 (proposta)

* Telas do app e exibição em R$ (Fase 4).
* Coleta real e arquitetura de coleta no aparelho do usuário (Fase 4 / melhorias da base).
* Qualquer item da seção 6.

### 7.4 Perguntas para o professor

1. Os limites quantitativos entram como **restrição rígida** (o modelo não deixa
   ultrapassar) ou só como **alerta**?
2. Bens de uso pessoal e itens fora da cota: modelar ou deixar fora do escopo?
3. A cota disponível continua sendo informada pelo usuário, ou o app passa a calcular pelo
   histórico de 30 dias?
4. Precisamos de instâncias novas com quantidades maiores que 1 (hoje todas têm
   `quantidade = 1`) para testar os limites por quantidade?
