# LesteShop — base de ofertas de Ciudad del Este e modelo de otimização

Projeto da disciplina de **Pesquisa Operacional II**. Objetivo final: o turista informa o que
quer comprar em Ciudad del Este e o app devolve onde comprar, o roteiro, o gasto total e a
situação frente à cota de isenção. O problema por trás é o *Traveling Purchaser Problem*
(Laporte, Riera-Ledesma e Salazar-González, 2003).

Seguindo o modelo cascata, o repositório contém:

* **Fase 1** — coleta, validação, banco de dados, catálogo de modelos e gerador de instâncias;
* **Fase 2** — modelo de otimização: TPP com mochila, cota de isenção, imposto sobre o
  excedente e janelas de tempo (PuLP + CBC e heurística). Ver
  [Fase 2](#fase-2--modelo-de-otimização) e [`docs/modelo_matematico.md`](docs/modelo_matematico.md).

Regras fiscais detalhadas e telas do app estão em [`docs/pendencias.md`](docs/pendencias.md).

## Estrutura

```
LestShop/
├── .github/workflows/      atualização semanal do catálogo
├── data/
│   ├── raw/                  base fictícia: 50 lojas, 73 produtos, 613 ofertas (sintetico)
│   ├── coletas/<data>/       coletas reais salvas em CSV (criada na primeira coleta)
│   ├── instances/            100 instâncias de teste (inst_001…inst_100) + geradas pelo generator
│   ├── resultados/           resultados dos experimentos da Fase 2 (CSV, soluções JSON, resumo)
│   ├── catalogo_modelos.csv  catálogo versionado (atualizado pelo GitHub Actions)
│   ├── lojas_complemento.csv coordenadas/prédios preenchidos à mão
│   ├── lesteshop.db          SQLite (não versionado; recriado a partir dos CSVs)
│   ├── cache/                páginas baixadas (não versionado)
│   └── export/               CSVs exportados para revisão (não versionado)
├── src/lesteshop/data/
│   ├── sources/              FonteDeOfertas (base.py), FonteCSV, FonteComprasParaguai, FonteAPI
│   ├── coletar.py            comando de coleta
│   ├── catalogo.py           catálogo + sugerir_modelos()
│   ├── cotacao.py            PTAX do Banco Central
│   ├── database.py           SQLite + lojas_que_vendem()
│   ├── validator.py          validação
│   ├── generator.py          instâncias sintéticas
│   └── resumo.py             resumo da base + exportação
├── src/lesteshop/otimizacao/ Fase 2: distancias, instancia, rota, solucao, modelo,
│                             heuristica, resolver (comando), experimentos
├── tests/                    pytest (fixtures HTML em tests/fixtures/)
└── docs/                     dicionário de dados, origem dos dados, pendências
```

## Testar pelo navegador, sem instalar nada

No GitHub, clique em **Code → Codespaces → Create codespace on main**. O ambiente
sobe com tudo instalado e roda os testes sozinho. Os comandos estão em
[`docs/testar_no_navegador.md`](docs/testar_no_navegador.md). A coleta real não roda lá
(precisa de uma tela para a verificação do site).

## Instalação

Python 3.11 ou mais novo.

```bash
git clone https://github.com/rairacunha/LestShop.git
cd LestShop
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## Como coletar um produto

O Compras Paraguai usa proteção anti-robô (Cloudflare) e responde 403 a acessos automáticos
comuns. Por isso a coleta é feita com `--navegador`: abre uma janela do Chromium e **você
resolve a verificação** do site quando ela aparecer. O LesteShop não tenta contornar a
proteção (sem plugins "stealth", sem resolver CAPTCHA automaticamente). Precisa de uma tela,
então rode no seu computador.

Instalação extra (uma vez):

```bash
pip install -e ".[dev,navegador]"
playwright install chromium
```

```bash
# ver quais modelos a busca encontra
python -m lesteshop.data.coletar "playstation 5 pro" --listar --navegador

# coletar as ofertas do primeiro modelo encontrado (padrão: 1 modelo por termo)
python -m lesteshop.data.coletar "playstation 5 pro" --navegador

# ou indicar a página do modelo diretamente
python -m lesteshop.data.coletar --url "https://www.comprasparaguai.com.br/<slug>_<id>/" --navegador
```

Quando aparecer no terminal *"O Compras Paraguai pediu uma verificação anti-robô"*, vá até a
janela do navegador, resolva a verificação e aguarde: a coleta continua sozinha. O perfil do
navegador fica em `data/cache/navegador/`, então a liberação vale para as próximas coletas
enquanto o site não pedir de novo. Prazo para resolver: 5 minutos.

Antes da primeira coleta, vale conferir o parser contra o HTML real:

```bash
python -m lesteshop.data.salvar_fixtures "playstation 5 pro" --navegador
pytest tests/test_fixtures_reais.py -v
```

A coleta espera 10 s entre requisições, respeita o `robots.txt`, guarda as páginas em cache e
mantém só as lojas de Ciudad del Este. O resultado vai para `data/coletas/<data>/*.csv` e para
`data/lesteshop.db`. As lojas sem coordenadas aparecem na saída: copie a posição do Google
Maps para `data/lojas_complemento.csv`:

```csv
loja_id,latitude,longitude,predio,observacao
CP-nome-da-loja,-25.51094,-54.60975,Shopping Exemplo,Google Maps 2026-10-20
```

Consultar quem vende um produto (mais barato primeiro):

```bash
python -m lesteshop.data.database --vendem "playstation 5 pro"
```

## Resumo e validação da base

```bash
python -m lesteshop.data.resumo             # usa o banco (ou cria a partir dos CSVs)
python -m lesteshop.data.resumo --recriar   # recria o banco a partir dos CSVs antes
```

O resumo mostra o número de lojas, produtos e ofertas; o menor e o maior preço de cada produto
e em quantas lojas ele aparece; as lojas com coordenada pendente; as ofertas descartadas por
cidade; e a cotação usada. Ele também exporta `lojas.csv`, `produtos.csv` e `ofertas.csv`
para `data/export/`.

Sem nenhuma coleta, o banco é criado a partir da base fictícia (`data/raw/`). Com coletas, a
base fictícia só entra se você passar `--incluir-semente`.

## Base fictícia (usada para concluir a Fase 1)

Como a coleta real depende da verificação anti-robô do site, a Fase 1 foi concluída com uma
base **fictícia** (todo `tipo_dado = "sintetico"`), gerada por
[`scripts/gerar_base_ficticia.py`](scripts/gerar_base_ficticia.py) com seed fixa 2026:

* `data/raw/`: 50 lojas em 8 prédios fictícios, 73 produtos genéricos em 14 categorias,
  613 ofertas (todo produto em pelo menos 2 lojas) e uma cotação fictícia (US$ 1 = R$ 5,14);
* `data/instances/inst_001…inst_100`: 40 pequenas, 35 médias e 25 grandes, cada uma com
  `lista_compras.csv` e parâmetros de cenário no `metadata.json` (cota, orçamento, horários).

Detalhes em [`data/LEIA-ME_base_ficticia.md`](data/LEIA-ME_base_ficticia.md). Para regerar
(resultado idêntico): `python scripts/gerar_base_ficticia.py`.

## Instâncias sintéticas

Tamanhos: pequena = 5 lojas × 10 produtos, média = 15 × 40, grande = 40 × 70. O gerador só
sorteia lojas e produtos que existem na base (não cria lojas nem produtos artificiais); se a base
for menor que o tamanho pedido, ele para com erro. Nos experimentos, use sempre o número real de
lojas registrado no `metadata.json` de cada instância.

```bash
python -m lesteshop.data.generator --size pequena --seed 42     # 5 lojas x 10 produtos
python -m lesteshop.data.generator --size media --seed 42       # 15 x 40
python -m lesteshop.data.generator --size grande --seed 42 --densidade 0.3 --variacao 0.15   # 40 x 70
python -m lesteshop.data.generator --size media --seed 1 --base banco   # parte da base coletada
```

Saída: `data/instances/<tamanho>_seed<seed>/` com os CSVs e um `metadata.json`. A mesma
seed (com a mesma base) gera exatamente a mesma instância.

## Catálogo de modelos (autocompletar)

```bash
python -m lesteshop.data.catalogo atualizar               # baixa o sitemap (demora: 10 s por arquivo)
python -m lesteshop.data.catalogo sugerir "playstation 5 pro"
```

Em Python:

```python
from lesteshop.data.catalogo import sugerir_modelos
sugerir_modelos("playstation 5 pro", limite=10)   # DataFrame; busca local, sem internet
```

A data da última atualização fica em `data/catalogo_meta.json`. Se a atualização falhar, o
CSV existente não é alterado.

## Atualização automática (GitHub Actions)

> **Atenção:** como o site exige verificação humana, o workflow automático tende a falhar
> (com mensagem clara e sem alterar o catálogo). Enquanto isso valer, atualize o catálogo
> no seu computador com `python -m lesteshop.data.catalogo atualizar --navegador` e faça
> commit de `data/catalogo_modelos.csv` e `data/catalogo_meta.json`.

O workflow **"Atualizar catálogo de modelos"** roda toda segunda-feira às 03:00 de Brasília
(`cron: "0 6 * * 1"`, em UTC). Ele roda os testes, atualiza o catálogo e faz commit só se o
CSV mudou, com a data e o número de modelos novos e removidos na mensagem.

* **Ver as execuções:** aba **Actions** do repositório → "Atualizar catálogo de modelos" no menu
  à esquerda. Uma execução vermelha mostra o motivo na anotação `::error::`.
* **Disparar manualmente:** na mesma página, botão **Run workflow** → escolher o branch → **Run
  workflow**.
* O agendamento só funciona com o workflow no branch padrão (`main`) do repositório.
* Em *Settings → Actions → General → Workflow permissions*, deixe "Read and write
  permissions" ativado para o bot poder fazer o commit.

## Cotação do dólar

```bash
python -m lesteshop.data.cotacao              # PTAX de venda de hoje ou do último dia útil
```

Todos os cálculos são feitos em US$; a cotação serve apenas para exibir valores em R$.

## Fase 2 — Modelo de otimização

O turista sai da Ponte da Amizade, visita lojas e volta. O modelo escolhe quais itens
comprar (pode deixar itens de fora se o orçamento ou o horário não comportarem), em qual
loja e em que ordem visitar, com uma única função objetivo:

```
max  Σ prioridade·comprado  −  λ·( gasto + 50%·excedente da cota  +  r·minutos andando )
λ = 1 / (orçamento + r·(saída − chegada) + 1)
```

λ garante que gasto e tempo valham menos que 1 ponto de prioridade; r (padrão
US$ 0,25/min) é quanto o turista aceita pagar para andar 1 minuto a menos. Formulação
completa, dedução de λ, big-M e hipóteses em [`docs/modelo_matematico.md`](docs/modelo_matematico.md).

```bash
# resolver uma instância (heurística → modelo exato com warm start → polimento da rota)
python -m lesteshop.otimizacao.resolver data/instances/inst_001_pequena

# variações
python -m lesteshop.otimizacao.resolver data/instances/inst_081_grande --r 1 --json saida.json
python -m lesteshop.otimizacao.resolver data/instances/inst_002_pequena --sem-orcamento
python -m lesteshop.otimizacao.resolver data/instances/inst_010_pequena --peso-max 10 --volume-max 40

# experimentos: 100 instâncias com r = 0,25 + sensibilidade r = 0 e r = 1 (pequenas e médias)
python -m lesteshop.otimizacao.experimentos --processos 3
python -m lesteshop.otimizacao.experimentos --so-resumo   # refaz só o resumo
```

A saída mostra os itens com loja e preço, o roteiro com horários, os itens deixados de
fora, o gasto, o imposto, a situação da cota, o tempo andando (antes e depois do polimento),
o peso e o volume da bagagem e o status do solver (gap, tempo, M). Os experimentos gravam
`data/resultados/resultados_fase2.csv`, `data/resultados/solucoes/r<r>/<instância>.json` e
`data/resultados/resumo_experimentos.md`.

Em Python:

```python
from lesteshop.otimizacao.instancia import carregar_instancia
from lesteshop.otimizacao.resolver import resolver
from lesteshop.otimizacao.solucao import descrever

inst = carregar_instancia("data/instances/inst_001_pequena")   # orcamento=None: sem orçamento
solucao, solucao_heuristica = resolver(inst, r=0.25)
descrever(solucao, inst)   # dicionário com itens, roteiro, gasto, imposto e cota
```

O solver é o CBC que vem com o PuLP (`pulp>=2.7,<4`; o PuLP 4 não traz mais o CBC).

## Documentação

* [Dicionário de dados](docs/dicionario_de_dados.md)
* [Modelo matemático da Fase 2](docs/modelo_matematico.md)
* [Resultados dos experimentos da Fase 2](data/resultados/resumo_experimentos.md)
* [Origem dos dados e limitações](docs/origem_dos_dados.md)
* [Pendências para as próximas fases](docs/pendencias.md)
