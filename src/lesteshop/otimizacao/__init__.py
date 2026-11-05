"""LesteShop — Fase 2: modelo de otimização (Traveling Purchaser Problem com mochila,
cota de isenção, imposto sobre o excedente e janelas de tempo).

Módulos:

* ``config``      — parâmetros padrão do modelo;
* ``distancias``  — matriz de tempos a pé (haversine × circuidade);
* ``instancia``   — leitura e pré-processamento de uma instância;
* ``rota``        — agenda de uma rota, 2-opt e polimento da ordem de visita;
* ``solucao``     — avaliação de uma solução (gasto, imposto, objetivo);
* ``modelo``      — modelo exato (PuLP + CBC);
* ``heuristica``  — heurística construtiva + busca local;
* ``resolver``    — comando para resolver uma instância;
* ``experimentos``— roda as 100 instâncias e gera os resultados.
"""
