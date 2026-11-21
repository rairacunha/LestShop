"""Consulta sob demanda ao Compras Paraguai (Fase 4).

Separado da otimização: este pacote só busca preços e lojas e devolve a matriz
Produto × Loja × Preço; quem calcula o roteiro é ``lesteshop.otimizacao`` (sem
mudanças), chamado pelo app.

* ``catalogo``: catálogo curado (``data/catalogo_app.json``) que popula o menu do app;
* ``cache``: cache local (SQLite) do resultado de cada item, com validade de 6 horas;
* ``busca``: consulta só os itens escolhidos pelo turista, com intervalo entre
  requisições, e monta a matriz e a base usada pelo app.
"""
