# Handoff para a Fase 5 — LesteShop

Documento autocontido para começar a Fase 5 (design do aplicativo). Repositório:
**`rairacunha/LestShop`**. Situação em 21/11/2026: Fases 1 a 4 concluídas; a Fase 5 foi
aberta e as decisões de design foram **aprovadas pela dona do projeto em 21/11/2026**
(seção 5). **Entrega do projeto: 23/11/2026** (2 dias). Não há tempo de consultar o
professor: as decisões da dona do projeto valem como finais nesta fase.

## 1. Contexto do projeto

O LesteShop é o projeto da disciplina de **Pesquisa Operacional II**. O turista informa o
que quer comprar em Ciudad del Este (Paraguai) e o app devolve onde comprar cada item, o
roteiro saindo e voltando à Ponte da Amizade, o gasto total e a situação frente à cota de
isenção e às regras de bagagem da Receita Federal. O problema por trás é o **Traveling
Purchaser Problem** (Laporte, Riera-Ledesma e Salazar-González, 2003), com mochila, cota,
imposto sobre o excedente e janelas de tempo.

### Regras de trabalho (obrigatórias)

* **Método cascata:** fazer **apenas a fase pedida**. O que for de outra fase vai para
  `docs/pendencias.md`, sem implementar.
* **Antes de implementar, apresentar a proposta** (opções e recomendação) e **esperar a
  aprovação** da dona do projeto, que valida as decisões com o professor.
* **Melhorias futuras NÃO são implementadas sem autorização explícita.** O objetivo é
  manter o app o mais simples possível.
* Respostas e documentação em português. O código segue o estilo de `src/lesteshop/`.
* Dados inventados nunca são marcados como `real` (`tipo_dado = "sintetico"`).
* Todos os cálculos em **US$**; o R$ é só para exibição.
* Rodar `pytest` antes de cada commit (hoje: **299 passam, 1 pulado**, o do navegador
  quando não há Playwright para Python).
* **Na Fase 5, o cálculo não muda:** modelo, regras fiscais, montagem da instância,
  consulta e base ficam como estão.

## 2. Como rodar

```bash
pip install -e ".[dev,app]"            # no computador; acrescente ",navegador" para coletar
streamlit run app.py                   # http://localhost:8501
pytest
```

* **Notebook da dona do projeto (Windows, PowerShell):** `git pull --no-edit` e
  `.venv\Scripts\python -m streamlit run app.py`. Se o Streamlit travar em "Stopping...",
  fechar a janela.
* **Web:** Streamlit Community Cloud, arquivo principal `app.py` (ele põe `src/` no caminho
  de importação). Num servidor sem tela, a consulta ao vivo fica escondida e o app usa a
  base guardada. O Cloud atualiza sozinho a cada `git push` no branch configurado.
* **Codespaces:** só a base guardada (não há tela para a verificação anti-robô).

## 3. O que as Fases 1 a 3 entregaram (resumo)

* **Fase 1 — base de dados:** coletor do Compras Paraguai (`--navegador`: a pessoa resolve
  a verificação anti-robô; o LesteShop não a contorna), validação, SQLite, base fictícia
  (`data/raw/`), 100 instâncias de teste, cotação PTAX.
* **Fase 2 — modelo:** max Σ v_k·y_k − λ·(G + α·E + r·Σ t_ij·x_ij), λ = 1/(B + r·T_max + 1),
  r = US$ 0,25/min; heurística → PuLP + CBC com warm start → polimento da ordem.
  `resolver()` + `descrever()` devolvem o resultado completo em JSON.
* **Fase 3 — regras fiscais:** tabela versionada `data/regras_fiscais.csv` (cota de
  US$ 500, alíquota de 50%, limites de bagagem), alertas, imposto sem cota, e-DBV.

Detalhes: `docs/handoff_fase4.md`, `docs/modelo_matematico.md`, `docs/legislacao_bagagem.md`.

## 4. Fase 4 — aplicativo (concluída em 21/11/2026)

### Arquitetura

```
app.py                         ponto de entrada (local e Streamlit Cloud)
src/lesteshop/app/
  base.py         base guardada (SQLite recriado de data/coletas/), coleta mais recente,
                  preço atípico, cotação do site
  pedido.py       validação + montar_pedido() (usa montar_instancia() da Fase 2);
                  teto_sem_limite() (orçamento só como referência)
  apresentacao.py tabelas e textos (US$/R$, roteiro, itens de fora, bloco fiscal,
                  comparativo com a compra avulsa)
  tela.py         interface Streamlit
src/lesteshop/consulta/        separado da otimização
  catalogo.py     catálogo curado data/catalogo_app.json (35 produtos)
  cache.py        cache SQLite data/cache/consulta.db, validade de 6 h
  busca.py        consulta só os itens da lista (1,5 s entre requisições), busca de
                  modelos no site, matriz Produto × Loja × Preço, grava na base guardada
```

### A tela hoje (visual padrão do Streamlit)

* **Barra lateral:** fonte dos preços (*Consulta ao Compras Paraguai* no computador; *Base
  guardada*), origem e data dos dados, cotação, dados da viagem (chegada, saída,
  orçamento opcional).
* **1. Lista de compras:** caixa de busca (palavras em qualquer ordem, sem acento) com
  botão "Adicionar"; se o produto não estiver na base, o app procura no site; lista com
  quantidade, prioridade 1–5 e botão de remover.
* **2. Calcular.**
* **3. Resultado:** aviso de orçamento ultrapassado; gasto, imposto e custo total (US$ e
  R$); onde comprar cada item; roteiro (Ponte → lojas → Ponte, com horários); comparativo
  compra avulsa (Shopping China) × roteiro, com a economia em R$ e %; itens de fora;
  preços encontrados (matriz); Receita Federal (cota, limites, declaração, premissa);
  avisos.

### Decisões da Fase 4 (não rediscutir sem motivo)

* Streamlit; uma página com barra lateral; valores em US$ com R$ ao lado.
* **Horário das lojas:** o do site (segunda a sexta); sem horário, padrão 07:00–16:00.
  **Coordenadas:** do site; `lojas_complemento.csv` só para correções.
* **Consulta sob demanda** (substitui a coleta em lote como caminho principal): só os itens
  da lista, cache de 6 h, 1,5 s entre requisições, robots.txt respeitado, sem contornar a
  verificação. Tudo o que é consultado entra na base guardada (`data/coletas/<data>/`).
* **Orçamento só como referência:** todos os itens entram no roteiro; o app avisa quanto o
  custo passa do orçamento. O modelo não mudou (recebe um B que não limita). Um item só
  fica de fora se não houver tempo; aí a prioridade decide.
* **Preço atípico:** oferta abaixo da metade da mediana do produto é descartada, com aviso.
* **Cotação mostrada:** a do Compras Paraguai, tirada das ofertas (R$ 5,95 em 20/11/2026).
* **Comparativo:** compra avulsa = tudo no Shopping China (o que ele não vende, pelo preço
  médio das lojas); economia = (avulsa − roteiro) ÷ avulsa.
* Data da viagem não é perguntada; r fixo em US$ 0,25/min.

### Dados

* Coleta real de 20/11/2026: 12 produtos, 55 lojas (todas com coordenadas, 38 com horário),
  816 ofertas. Exemplo: iPad, Switch 2, iPhone 16, mouse MX Master e DualSense → economia
  de US$ 117 (4,6%) em relação à compra avulsa.

## 5. Fase 5 — design do aplicativo: decisões aprovadas (21/11/2026)

A proposta foi apresentada e aprovada. **Não é preciso apresentar a proposta de novo:**
implementar, mostrando prints (computador) para a dona do projeto conferir.

1. **Cores — opção 1: azul e vermelho** (referência discreta ao Paraguai; bom contraste,
   ideia de "guia de compras"). Tema do Streamlit em `.streamlit/config.toml`
   (`[theme]`: cor principal, fundo, texto, fonte). Fundo claro.
2. **Logotipo: fica para o final; a dona do projeto vai criar.** Deixar o lugar pronto
   (ex.: `st.logo` com um arquivo em `assets/`), sem inventar um logotipo.
3. **Resultado numa página só** (sem abas), com títulos mais claros e um resumo no topo
   do resultado (custo total, economia, hora de volta à Ponte, situação da cota).
4. **Linguagem mais simples para o turista** em toda a tela: títulos como "Quanto você
   vai pagar", "Onde comprar", "Seu roteiro"; explicações curtas de cota, e-DBV,
   prioridade e orçamento; menos termos técnicos ("instância", "ótimo", "gap" não aparecem).
5. **Mapa do roteiro** (pedido em 20/11/2026): Ponte da Amizade, lojas numeradas na ordem
   da visita e volta à Ponte; ao passar o mouse, horário e o que comprar. pydeck (já vem
   com o Streamlit), mapa de fundo gratuito sem chave. Linhas retas entre as paradas
   (rotas pelas ruas continuam como pendência) — deixar isso claro numa legenda.
6. **Versão para celular: fora por enquanto.**

**Situação em 21/11/2026:** itens 1 a 5 implementados no branch `claude/fase5-design`
(resumo em `docs/pendencias.md`, seção da Fase 5). Falta só o arquivo do logotipo
(`assets/logo.png`), que a dona do projeto vai criar. Também foi implementado, com
autorização da dona do projeto, o **acréscimo por forma de pagamento** (única mudança de
cálculo da fase; detalhes em `docs/pendencias.md`).

Regras da Fase 5: o **cálculo não muda** (modelo, regras fiscais, montagem da instância,
consulta e base). Mudanças só em `src/lesteshop/app/tela.py`, `apresentacao.py` (textos),
tema e documentação; os testes da tela (`tests/test_app.py`, `tests/test_consulta.py`)
procuram alguns textos — atualizar junto. Rodar `pytest` antes de cada commit.

Fora da Fase 5: troca manual da ordem das lojas no mapa, versão para celular, qualquer
mudança no modelo ou nas regras, coleta automática num servidor, contas de usuário.

## 6. Pendências abertas (detalhes em `docs/pendencias.md`)

* Lentidão da instância grande no Windows (não afeta o app).
* Segundo e-mail ao Compras Paraguai (ajustar o texto: a consulta do app usa 1,5 s).
* Validação com o professor das decisões da Fase 4 que mudaram regras aprovadas.
* Experimentos da Fase 2 com dados reais.
