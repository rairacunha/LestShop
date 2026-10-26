"""Gera uma base FICTÍCIA de lojas, produtos e ofertas de Ciudad del Este
no formato da Fase 1 do LesteShop, e 100 instâncias de teste a partir dela.

Todos os dados são sintéticos (tipo_dado = "sintetico"): nomes de lojas e
prédios são inventados; coordenadas são sorteadas dentro da área central.
Uso: python scripts/gerar_base_ficticia.py  (seed fixa = reprodutível; escreve em data/)
"""
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SEED_BASE = 2026
DATA_COLETA = "2026-10-26"
FONTE = "ficticio (gerado para teste da Fase 1)"
SAIDA = Path(__file__).resolve().parents[1]  # raiz do projeto
rng = np.random.default_rng(SEED_BASE)

# --------------------------------------------------------------------------
# 1. Prédios (shoppings/galerias) fictícios com centro aproximado
#    Faixa de validação: lat -25.53 a -25.49, lon -54.63 a -54.59
# --------------------------------------------------------------------------
predios = {
    "Galeria Aurora":        (-25.5085, -54.6105),
    "Shopping Monte Azul":   (-25.5098, -54.6122),
    "Centro Comercial Rio":  (-25.5112, -54.6098),
    "Torre Fronteira":       (-25.5071, -54.6131),
    "Paseo Las Palmas":      (-25.5126, -54.6140),
    "Galeria Puente":        (-25.5060, -54.6088),
    "Plaza Comercial Este":  (-25.5140, -54.6115),
    "Rua (loja de rua)":     None,  # lojas avulsas: coordenada sorteada
}

prefixos = ["Mega", "Super", "Top", "Prime", "Nova", "Star", "Gold", "Max",
            "Flash", "Ultra", "Royal", "Smart", "Rapid", "Delta", "Sol", "Luna"]
sufixos = ["Imports", "Store", "Center", "Shop", "Eletrônicos", "Games",
           "Perfumes", "Tech", "Bazar", "Outlet", "Digital", "Mix"]

N_LOJAS = 50
nomes_lojas = set()
while len(nomes_lojas) < N_LOJAS:
    nomes_lojas.add(f"{rng.choice(prefixos)} {rng.choice(sufixos)} (fictícia)")
nomes_lojas = sorted(nomes_lojas)

lojas = []
nomes_predios = list(predios)
for i, nome in enumerate(nomes_lojas, start=1):
    predio = rng.choice(nomes_predios, p=[.14, .14, .14, .12, .12, .1, .1, .14])
    centro = predios[predio]
    if centro is None:
        lat = rng.uniform(-25.520, -25.500)
        lon = rng.uniform(-54.625, -54.600)
    else:  # lojas do mesmo prédio ficam a poucos metros umas das outras
        lat = centro[0] + rng.normal(0, 0.00015)
        lon = centro[1] + rng.normal(0, 0.00015)
    abre = rng.choice(["07:00", "07:30", "08:00"])
    fecha = rng.choice(["15:00", "16:00", "16:30", "17:00"])
    slug = nome.lower().replace(" (fictícia)", "").replace(" ", "-") \
        .replace("ô", "o").replace("ó", "o")
    lojas.append({
        "loja_id": f"L{i:03d}", "nome": nome, "slug": slug,
        "cidade": "Ciudad del Este", "endereco": f"{predio}, CDE (fictício)",
        "predio": predio, "latitude": round(lat, 6), "longitude": round(lon, 6),
        "coordenada_pendente": False, "abre": abre, "fecha": fecha,
        "tempo_permanencia_min": int(rng.choice([10, 15, 20, 25, 30])),
        "fonte": FONTE, "tipo_dado": "sintetico",
    })
lojas = pd.DataFrame(lojas)

# --------------------------------------------------------------------------
# 2. Catálogo de produtos fictícios (nome genérico, preço-base plausível)
#    (nome, categoria, preço-base US$, peso kg, volume L)
# --------------------------------------------------------------------------
catalogo = [
    # Eletrônicos / celulares
    ("Celular Modelo A 128GB", "Celulares", 210, 0.45, 1.2),
    ("Celular Modelo A 256GB", "Celulares", 260, 0.45, 1.2),
    ("Celular Modelo B Pro 256GB", "Celulares", 780, 0.50, 1.3),
    ("Celular Modelo B Pro Max 512GB", "Celulares", 1150, 0.55, 1.4),
    ("Celular Modelo C Lite 64GB", "Celulares", 120, 0.40, 1.1),
    ("Celular Modelo D 5G 128GB", "Celulares", 330, 0.45, 1.2),
    ("Smartwatch Esportivo S1", "Eletrônicos", 95, 0.25, 0.6),
    ("Smartwatch Premium S3", "Eletrônicos", 320, 0.30, 0.7),
    ("Fone Bluetooth Intra Básico", "Áudio", 25, 0.10, 0.3),
    ("Fone Bluetooth Intra com Cancelamento", "Áudio", 150, 0.15, 0.4),
    ("Headphone Over-Ear Wireless", "Áudio", 210, 0.60, 3.5),
    ("Caixa de Som Portátil Mini", "Áudio", 45, 0.40, 1.0),
    ("Caixa de Som Portátil Grande", "Áudio", 180, 2.80, 9.0),
    ("Soundbar 2.1 Canais", "Áudio", 230, 6.50, 25.0),
    ("Câmera de Ação 4K", "Eletrônicos", 260, 0.50, 1.5),
    ("Drone Compacto com Câmera", "Eletrônicos", 410, 1.20, 5.0),
    ("Carregador Portátil 20000mAh", "Eletrônicos", 30, 0.45, 0.6),
    ("Kindle-like Leitor Digital 6\"", "Eletrônicos", 110, 0.35, 0.9),
    ("Smart TV 50\" 4K", "TV", 380, 14.0, 95.0),
    ("Streaming Stick HD", "TV", 35, 0.20, 0.4),
    # Games
    ("Console de Mesa Geração Atual 1TB", "Games", 520, 4.50, 30.0),
    ("Console de Mesa Pro 2TB", "Games", 790, 5.00, 32.0),
    ("Console Portátil Híbrido", "Games", 340, 1.30, 5.5),
    ("Controle Sem Fio Console", "Games", 65, 0.40, 1.5),
    ("Jogo Mídia Física Lançamento", "Games", 60, 0.12, 0.3),
    ("Jogo Mídia Física Catálogo", "Games", 30, 0.12, 0.3),
    ("Headset Gamer 7.1", "Games", 70, 0.70, 3.0),
    # Informática
    ("Notebook Ultrafino 16GB/512GB", "Informática", 750, 2.20, 8.0),
    ("Notebook Gamer RTX 16GB/1TB", "Informática", 1100, 3.50, 12.0),
    ("Tablet 10\" 128GB", "Informática", 290, 0.90, 2.5),
    ("Mouse Sem Fio", "Informática", 18, 0.15, 0.5),
    ("Teclado Mecânico RGB", "Informática", 55, 1.10, 4.0),
    ("SSD Externo 1TB", "Informática", 85, 0.15, 0.3),
    ("Pendrive 128GB", "Informática", 12, 0.05, 0.1),
    ("Monitor 27\" QHD", "Informática", 230, 6.80, 35.0),
    ("Roteador Wi-Fi 6", "Informática", 70, 0.90, 3.0),
    ("Placa de Vídeo Intermediária 8GB", "Informática", 340, 1.40, 6.0),
    ("Memória RAM 16GB DDR5", "Informática", 55, 0.10, 0.2),
    # Perfumaria e cosméticos
    ("Perfume Feminino Floral 100ml", "Perfumes", 85, 0.45, 0.6),
    ("Perfume Feminino Oriental 50ml", "Perfumes", 65, 0.30, 0.4),
    ("Perfume Masculino Amadeirado 100ml", "Perfumes", 78, 0.45, 0.6),
    ("Perfume Masculino Cítrico 200ml", "Perfumes", 95, 0.70, 0.9),
    ("Perfume Árabe Unissex 100ml", "Perfumes", 35, 0.50, 0.7),
    ("Kit Maquiagem Básico", "Cosméticos", 40, 0.50, 1.0),
    ("Sérum Facial Vitamina C 30ml", "Cosméticos", 22, 0.12, 0.2),
    ("Protetor Solar FPS 50 200ml", "Cosméticos", 18, 0.25, 0.3),
    ("Secador de Cabelo Profissional", "Beleza", 65, 0.90, 4.0),
    ("Prancha Alisadora Titânio", "Beleza", 48, 0.60, 2.0),
    ("Barbeador Elétrico", "Beleza", 75, 0.50, 1.2),
    # Bebidas
    ("Whisky 12 anos 1L", "Bebidas", 38, 1.60, 1.5),
    ("Whisky 18 anos 750ml", "Bebidas", 95, 1.40, 1.3),
    ("Vodka Premium 1L", "Bebidas", 22, 1.50, 1.4),
    ("Gin Importado 750ml", "Bebidas", 28, 1.30, 1.2),
    ("Vinho Tinto Reserva 750ml", "Bebidas", 15, 1.30, 1.1),
    ("Espumante Brut 750ml", "Bebidas", 20, 1.50, 1.2),
    # Casa, lazer e outros
    ("Garrafa Térmica 1L", "Lazer", 35, 0.60, 1.8),
    ("Copo Térmico 473ml", "Lazer", 28, 0.40, 1.0),
    ("Molinete de Pesca", "Lazer", 60, 0.40, 1.2),
    ("Vara de Pesca Telescópica", "Lazer", 45, 0.70, 3.0),
    ("Barraca Camping 4 Pessoas", "Lazer", 90, 4.50, 18.0),
    ("Brinquedo Blocos de Montar 500pç", "Brinquedos", 45, 1.00, 4.0),
    ("Boneca Articulada Colecionável", "Brinquedos", 30, 0.50, 2.0),
    ("Carrinho Controle Remoto", "Brinquedos", 55, 1.20, 6.0),
    ("Air Fryer 5L", "Casa", 75, 4.80, 22.0),
    ("Robô Aspirador", "Casa", 210, 3.50, 14.0),
    ("Liquidificador Potente 1200W", "Casa", 55, 3.80, 12.0),
    ("Cafeteira de Cápsulas", "Casa", 85, 3.20, 11.0),
    ("Jogo de Panelas Antiaderente 5pç", "Casa", 95, 6.00, 28.0),
    ("Óculos de Sol Polarizado", "Moda", 70, 0.15, 0.5),
    ("Relógio Analógico Aço", "Moda", 120, 0.25, 0.6),
    ("Tênis Esportivo Corrida", "Moda", 80, 0.90, 7.0),
    ("Mochila Notebook 15\"", "Moda", 40, 0.80, 20.0),
    ("Mala de Bordo 10kg", "Moda", 70, 2.80, 40.0),
]

produtos = pd.DataFrame([{
    "produto_id": f"P{i:03d}", "nome": n, "categoria": c,
    "url_modelo": "", "peso_kg": w, "volume_l": v,
    "preco_base_usd": p, "tipo_dado": "sintetico",
} for i, (n, c, p, w, v) in enumerate(catalogo, start=1)])

# --------------------------------------------------------------------------
# 3. Ofertas: cada loja tem um "perfil" de categorias; preço varia ±15%
#    em torno do preço-base, com um viés próprio de cada loja (cara/barata).
# --------------------------------------------------------------------------
categorias = sorted(produtos["categoria"].unique())
ofertas = []
for _, loja in lojas.iterrows():
    n_cat = rng.integers(2, 6)
    foco = set(rng.choice(categorias, size=n_cat, replace=False))
    vies = rng.normal(0, 0.05)  # loja tende a ser mais cara ou mais barata
    for _, prod in produtos.iterrows():
        prob = 0.55 if prod["categoria"] in foco else 0.05
        if rng.random() < prob:
            fator = 1 + vies + rng.uniform(-0.15, 0.15)
            preco = round(prod["preco_base_usd"] * fator, 2)
            # arredondamento "de etiqueta" (ex.: 209,90 / 210,00)
            preco = float(np.floor(preco)) + rng.choice([0.0, 0.90, 0.99])
            ofertas.append({
                "loja_id": loja["loja_id"], "produto_id": prod["produto_id"],
                "titulo_oferta": f"{prod['nome']} - {loja['nome']}",
                "codigo_loja": str(rng.integers(10000, 999999)),
                "preco_usd": round(preco, 2), "preco_brl": None,
                "data_coleta": DATA_COLETA, "fonte": FONTE,
                "tipo_dado": "sintetico",
            })
ofertas = pd.DataFrame(ofertas)

# Garante que todo produto tenha pelo menos 2 ofertas (regra do validador
# exige >= 1; com >= 2 sempre existe escolha de loja, que é a essência do TPP)
for pid in produtos["produto_id"]:
    n = (ofertas["produto_id"] == pid).sum()
    if n < 2:
        prod = produtos.set_index("produto_id").loc[pid]
        ja = set(ofertas.loc[ofertas["produto_id"] == pid, "loja_id"])
        livres = [l for l in lojas["loja_id"] if l not in ja]
        for lid in rng.choice(livres, size=2 - n, replace=False):
            preco = round(prod["preco_base_usd"] * (1 + rng.uniform(-.15, .15)), 2)
            nome_loja = lojas.set_index("loja_id").loc[lid, "nome"]
            ofertas.loc[len(ofertas)] = {
                "loja_id": lid, "produto_id": pid,
                "titulo_oferta": f"{prod['nome']} - {nome_loja}",
                "codigo_loja": str(rng.integers(10000, 999999)),
                "preco_usd": preco, "preco_brl": None, "data_coleta": DATA_COLETA,
                "fonte": FONTE, "tipo_dado": "sintetico"}

# Cotação fictícia para exibição em R$ (cálculos do modelo ficam em US$)
COTACAO = 5.14
ofertas["preco_brl"] = (ofertas["preco_usd"] * COTACAO).round(2)

# Regra: loja só entra se tiver ao menos uma oferta
lojas = lojas[lojas["loja_id"].isin(ofertas["loja_id"])].reset_index(drop=True)

pontos_partida = pd.DataFrame([{
    "id": 0, "nome": "Ponte da Amizade (lado paraguaio)",
    "latitude": -25.5097, "longitude": -54.6033}])
cotacoes = pd.DataFrame([{"data": DATA_COLETA, "valor_brl_por_usd": COTACAO,
                          "fonte": "valor fictício para teste"}])

# --------------------------------------------------------------------------
# 4. Salva a base completa
# --------------------------------------------------------------------------
raw = SAIDA / "data" / "raw"
raw.mkdir(parents=True, exist_ok=True)
lojas.to_csv(raw / "lojas.csv", index=False)
produtos.to_csv(raw / "produtos.csv", index=False)
ofertas.to_csv(raw / "ofertas.csv", index=False)
pontos_partida.to_csv(raw / "pontos_partida.csv", index=False)
cotacoes.to_csv(raw / "cotacoes.csv", index=False)

# --------------------------------------------------------------------------
# 5. 100 instâncias de teste
#    40 pequenas (5 lojas/10 prod), 35 médias (15/40), 25 grandes (40/70)
#    Cada instância = subconjunto de lojas + produtos da base + lista de
#    compras do usuário (com prioridade) + parâmetros do cenário.
# --------------------------------------------------------------------------
tamanhos = ([("pequena", 5, 10)] * 40 + [("media", 15, 40)] * 35
            + [("grande", 40, 70)] * 25)
inst_dir = SAIDA / "data" / "instances"
resumo = []

for k, (tam, n_l, n_p) in enumerate(tamanhos, start=1):
    seed = SEED_BASE * 1000 + k
    r = np.random.default_rng(seed)
    densidade = round(float(r.uniform(0.25, 0.60)), 2)

    lojas_i = lojas.sample(n=n_l, random_state=seed)
    ids_l = set(lojas_i["loja_id"])
    of_i = ofertas[ofertas["loja_id"].isin(ids_l)].copy()

    # produtos que tenham ao menos 2 ofertas dentro dessas lojas
    cont = of_i["produto_id"].value_counts()
    elegiveis = list(cont[cont >= 2].index)
    if len(elegiveis) < n_p:  # completa com produtos de 1 oferta
        elegiveis += list(cont[cont == 1].index)
    ids_p = list(r.choice(sorted(elegiveis), size=min(n_p, len(elegiveis)),
                          replace=False))
    of_i = of_i[of_i["produto_id"].isin(ids_p)]

    # densidade: descarta parte das ofertas, mantendo >=1 por produto
    manter = []
    for pid, g in of_i.groupby("produto_id"):
        alvo = max(1, int(round(len(g) * max(densidade, 1 / len(g)) * 1.6)))
        manter.append(g.sample(n=min(alvo, len(g)), random_state=seed))
    of_i = pd.concat(manter)
    prod_i = produtos[produtos["produto_id"].isin(of_i["produto_id"])]
    lojas_i = lojas_i[lojas_i["loja_id"].isin(of_i["loja_id"])]

    # lista de compras do usuário (turista compra poucos itens), prioridade 1-5
    faixa = {"pequena": (3, 6), "media": (4, 10), "grande": (6, 15)}[tam]
    n_lista = min(len(prod_i), int(r.integers(faixa[0], faixa[1] + 1)))
    # metade das instâncias favorece itens baratos (lista tende a caber na cota)
    pesos = np.ones(len(prod_i))
    if k % 2 == 0:  # só itens de até US$ 100, quando houver suficientes
        baratos = (prod_i["preco_base_usd"] <= 100).to_numpy()
        if baratos.sum() >= n_lista:
            pesos = baratos.astype(float)
    idx = r.choice(len(prod_i), size=n_lista, replace=False, p=pesos / pesos.sum())
    lista = prod_i.iloc[sorted(idx)][["produto_id", "nome"]].copy()
    lista["quantidade"] = 1
    lista["prioridade"] = r.integers(1, 6, size=len(lista))

    # cenário: cota disponível, orçamento e tempo
    cota = float(r.choice([500, 500, 500, 300, 150]))  # parte já usada
    menor_por_prod = of_i.groupby("produto_id")["preco_usd"].min()
    custo_min_lista = float(menor_por_prod.loc[lista["produto_id"]].sum())
    orcamento = round(custo_min_lista * float(r.uniform(0.6, 1.4)), 2)
    chegada = r.choice(["07:30", "08:00", "09:00", "10:00"])
    saida = r.choice(["12:00", "13:00", "14:00", "15:00", "16:00"])

    nome_inst = f"inst_{k:03d}_{tam}"
    d = inst_dir / nome_inst
    d.mkdir(parents=True, exist_ok=True)
    lojas_i.to_csv(d / "lojas.csv", index=False)
    prod_i.to_csv(d / "produtos.csv", index=False)
    of_i.to_csv(d / "ofertas.csv", index=False)
    lista.to_csv(d / "lista_compras.csv", index=False)
    pontos_partida.to_csv(d / "pontos_partida.csv", index=False)

    meta = {
        "nome": nome_inst, "tamanho": tam, "seed": seed, "densidade": densidade,
        "n_lojas": len(lojas_i), "n_produtos": len(prod_i), "n_ofertas": len(of_i),
        "n_itens_lista": len(lista),
        "cota_disponivel_usd": cota, "aliquota_excedente": 0.5,
        "orcamento_usd": orcamento,
        "custo_minimo_lista_usd": round(custo_min_lista, 2),
        "lista_excede_cota": custo_min_lista > cota,
        "horario_chegada": str(chegada), "horario_saida": str(saida),
        "data_geracao": DATA_COLETA, "tipo_dado": "sintetico",
    }
    (d / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    resumo.append(meta)

pd.DataFrame(resumo).to_csv(inst_dir / "resumo_instancias.csv", index=False)

# --------------------------------------------------------------------------
# 6. LEIA-ME
# --------------------------------------------------------------------------
(SAIDA / "data" / "LEIA-ME_base_ficticia.md").write_text(f"""# Base fictícia LesteShop — teste da Fase 1

**Todos os dados são FICTÍCIOS** (tipo_dado = "sintetico"). Nomes de lojas e prédios
foram inventados; coordenadas foram sorteadas na área central de Ciudad del Este;
preços são plausíveis, mas não correspondem a nenhuma loja real. Não use para
decisões de compra.

## Base completa (data/raw/)
- lojas.csv — {len(lojas)} lojas em 8 prédios/galerias fictícios (lojas do mesmo
  prédio ficam a poucos metros, para testar deslocamento quase zero)
- produtos.csv — {len(produtos)} produtos em {produtos['categoria'].nunique()} categorias,
  com peso e volume (inclui a coluna extra preco_base_usd, usada só para gerar)
- ofertas.csv — {len(ofertas)} ofertas; todo produto tem pelo menos 2 lojas
- pontos_partida.csv — nó 0 (Ponte da Amizade)
- cotacoes.csv — cotação fictícia US$ 1 = R$ {COTACAO}

## 100 instâncias (data/instances/)
- 40 pequenas (5 lojas, 10 produtos), 35 médias (15 lojas, 40 produtos),
  25 grandes (40 lojas, até 70 produtos)
- Cada pasta tem lojas, produtos, ofertas, pontos_partida, **lista_compras.csv**
  (3 a 15 itens desejados, com prioridade 1–5) e metadata.json (seed, densidade,
  cota disponível, orçamento, horários de chegada e saída)
- resumo_instancias.csv lista todas lado a lado
- Os cenários variam de propósito: algumas listas cabem na cota, outras excedem;
  a cota disponível às vezes é menor que 500 (parte já usada no mês).

Regenerar: `python scripts/gerar_base_ficticia.py` (seed fixa {SEED_BASE}, resultado idêntico).
""", encoding="utf-8")

print("lojas", len(lojas), "| produtos", len(produtos), "| ofertas", len(ofertas))
print(pd.DataFrame(resumo).groupby("tamanho")[
    ["n_lojas", "n_produtos", "n_ofertas", "n_itens_lista"]].mean().round(1))
print("instâncias com lista acima da cota:",
      sum(m["lista_excede_cota"] for m in resumo))
