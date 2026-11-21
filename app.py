"""Aplicativo LesteShop (Fase 4). Rodar na raiz do projeto: streamlit run app.py

Também é o arquivo principal no Streamlit Community Cloud. Como o código fica em
src/ (e o Cloud não instala o pacote), a pasta src/ entra no caminho de importação.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lesteshop.app.tela import main  # noqa: E402

main()
