# Logotipo do LesteShop (lugar reservado)

O logotipo vai ser criado pela dona do projeto (decisão da Fase 5, 21/11/2026).

Para ele aparecer no app, basta salvar a imagem aqui com o nome **`logo.png`**
(fundo transparente, de preferência mais larga do que alta, por exemplo 600 × 200 px).
Não é preciso mexer no código: `src/lesteshop/app/tela.py` mostra o logotipo no canto
de cima da barra lateral (`st.logo`) sempre que `assets/logo.png` existir. Enquanto o
arquivo não existir, a tela mostra só o nome "LesteShop".

Cores do tema (em `.streamlit/config.toml`), para combinar com o logotipo:

| Uso | Cor |
|---|---|
| Azul (cor principal: botões, destaques, lojas no mapa) | `#0038A8` |
| Vermelho (alertas, Ponte da Amizade no mapa) | `#D52B1E` |
| Texto | `#1B2333` |
| Fundo da barra lateral e das caixas | `#EEF3FB` |
| Fundo | `#FFFFFF` |
