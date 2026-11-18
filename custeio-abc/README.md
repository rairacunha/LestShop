# Custeio ABC do Escritório

Site estático (sem backend) com os custeios do escritório pelo método ABC. Primeiro módulo:
**Emissão de Notas Fiscais (NIBO + Claude Pro)**.

Abra `index.html` no navegador (ou publique a pasta no GitHub Pages). Não precisa de build.

| Arquivo | Conteúdo |
|---|---|
| `index.html` | estrutura das 8 seções |
| `style.css` | visual, tema claro/escuro, celular e impressão |
| `app.js` | modelo ABC (seção 3.4 da especificação), simulador, cronoanálise e exportação |
| `data/processos.js` | parâmetros padrão e origem de cada um (informado / estimativa / preencher) |

Os valores ficam no `localStorage` do navegador (chave `custeioABC.v1`).
No console, `CUSTEIO_TESTE()` devolve o cálculo com os valores padrão (Cenário A = 13,85; B = 10,23).

Para um novo processo: acrescente um item em `processos` de `data/processos.js` e a função de
cálculo em `MODELOS` (`app.js`).
