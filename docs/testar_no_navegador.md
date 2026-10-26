# Testar a Fase 1 pelo navegador (GitHub Codespaces)

O Codespaces abre este repositório num computador na nuvem, com Python e as
dependências já instalados. Os testes rodam sozinhos na primeira abertura.

Abra o terminal (menu ☰ → Terminal → New Terminal) e rode:

| Critério de aceite | Comando | Esperado |
|---|---|---|
| Testes | `pytest` | `76 passed, 4 skipped` (os testes do navegador e das páginas reais são pulados aqui) |
| Gerador | `python -m lesteshop.data.generator --size pequena --seed 42` | instância em `data/instances/pequena_seed42/` |
| Resumo e validação | `python -m lesteshop.data.resumo --recriar` | 8 lojas, 18 produtos, 72 ofertas, "Validação: OK"; CSVs em `data/export/` |
| Consulta | `python -m lesteshop.data.database --vendem "playstation 5 pro"` | lojas da mais barata para a mais cara |

Para ver os arquivos gerados, abra `data/export/` ou `data/instances/` no explorador
à esquerda.

## O que não funciona no Codespaces

A **coleta real** do Compras Paraguai. O site pede uma verificação anti-robô e o
Codespaces não tem janela de navegador para você resolvê-la. Para a coleta real,
use um computador com tela (veja o README, seção "Como coletar um produto").

A cotação PTAX pode funcionar ou não, conforme a rede do Codespaces; se falhar, o
resumo mostra "Cotação usada: indisponível" e continua normalmente.
