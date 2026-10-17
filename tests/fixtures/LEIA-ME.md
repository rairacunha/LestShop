# Fixtures de teste

**Atenção:** estes arquivos HTML/XML foram escritos à mão imitando a estrutura
esperada do Compras Paraguai (links `/<slug>_<id>/` e `/lojas/<slug>/`, preços
com `US$` e `R$`). Eles **não** são cópias de páginas reais, porque o ambiente
em que a Fase 1 foi desenvolvida não tinha acesso ao site. As lojas citadas
são fictícias.

Para testar o parser contra páginas reais, rode (com internet):

    python -m lesteshop.data.salvar_fixtures "playstation 5 pro"

Isso salva a busca, a primeira página de modelo e as páginas das lojas em
`tests/fixtures/reais/`. O teste `tests/test_fixtures_reais.py` passa a
verificar essas páginas automaticamente (e é pulado quando a pasta não existe).
