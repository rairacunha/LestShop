"""Validação da base de ofertas (seção 9), com mensagens em português."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

import pandas as pd

from . import config, esquema
from .texto import dentro_de_cde, eh_ciudad_del_este

_RE_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ErroValidacao(ValueError):
    def __init__(self, erros: list[str]):
        self.erros = erros
        super().__init__("A base de ofertas é inválida:\n- " + "\n- ".join(erros))


@dataclass
class ResultadoValidacao:
    lojas: pd.DataFrame
    produtos: pd.DataFrame
    ofertas: pd.DataFrame
    erros: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    lojas_descartadas: list[str] = field(default_factory=list)
    ofertas_sem_preco: int = 0

    @property
    def ok(self) -> bool:
        return not self.erros

    def levantar_se_invalido(self) -> "ResultadoValidacao":
        if self.erros:
            raise ErroValidacao(self.erros)
        return self


def _lista(valores, limite: int = 10) -> str:
    valores = [str(v) for v in valores]
    texto = ", ".join(valores[:limite])
    return texto + (f" (e mais {len(valores) - limite})" if len(valores) > limite else "")


def validar(
    lojas: pd.DataFrame,
    produtos: pd.DataFrame,
    ofertas: pd.DataFrame,
    hoje: dt.date | None = None,
    dias_alerta: int = config.DIAS_VALIDADE_OFERTA,
) -> ResultadoValidacao:
    """Confere a base e devolve as tabelas limpas, os erros e os alertas.

    Erros tornam a base inválida. Lojas sem ofertas e ofertas sem preço não
    são erros: são descartadas e listadas no resultado.
    """
    hoje = hoje or dt.date.today()
    erros: list[str] = []
    alertas: list[str] = []

    faltando = {
        nome: [c for c in esquema.COLUNAS[nome] if c not in df.columns]
        for nome, df in (("lojas", lojas), ("produtos", produtos), ("ofertas", ofertas))
    }
    faltando = {k: v for k, v in faltando.items() if v}
    if faltando:
        erros += [f"Tabela '{t}' sem as colunas obrigatórias: {_lista(c)}." for t, c in faltando.items()]
        return ResultadoValidacao(lojas, produtos, ofertas, erros=erros)

    lojas = esquema.padronizar(lojas, "lojas")
    produtos = esquema.padronizar(produtos, "produtos")
    ofertas = esquema.padronizar(ofertas, "ofertas")

    # --- ids ---------------------------------------------------------------
    for nome, df, col in (("lojas", lojas, "loja_id"), ("produtos", produtos, "produto_id")):
        if df[col].isna().any():
            erros.append(f"Há {int(df[col].isna().sum())} registro(s) em '{nome}' sem {col}.")
        dup = df.loc[df[col].duplicated(keep=False) & df[col].notna(), col].unique()
        if len(dup):
            erros.append(f"{col} repetido em '{nome}': {_lista(dup)}.")

    # --- tipo_dado e fonte -----------------------------------------------------
    for nome, df in (("lojas", lojas), ("produtos", produtos), ("ofertas", ofertas)):
        invalidos = df.loc[~df["tipo_dado"].isin(config.TIPOS_DADO), "tipo_dado"].unique()
        if len(invalidos):
            erros.append(f"tipo_dado inválido em '{nome}': {_lista(invalidos)} "
                         f"(use {', '.join(config.TIPOS_DADO)}).")

    # --- referências das ofertas ------------------------------------------------
    sem_loja = ofertas.loc[~ofertas["loja_id"].isin(lojas["loja_id"]), "loja_id"].unique()
    if len(sem_loja):
        erros.append(f"Ofertas apontam para lojas inexistentes: {_lista(sem_loja)}.")
    sem_produto = ofertas.loc[~ofertas["produto_id"].isin(produtos["produto_id"]), "produto_id"].unique()
    if len(sem_produto):
        erros.append(f"Ofertas apontam para produtos inexistentes: {_lista(sem_produto)}.")

    # --- preços -----------------------------------------------------------------
    sem_preco = ofertas["preco_usd"].isna()
    ofertas_sem_preco = int(sem_preco.sum())
    if ofertas_sem_preco:
        alertas.append(f"{ofertas_sem_preco} oferta(s) sem preco_usd foram descartadas.")
        ofertas = ofertas.loc[~sem_preco].reset_index(drop=True)
    for col in ("preco_usd", "preco_brl"):
        ruins = ofertas[ofertas[col].notna() & (ofertas[col] <= 0)]
        if len(ruins):
            pares = [f"{r.loja_id}/{r.produto_id}={getattr(r, col)}" for r in ruins.itertuples()]
            erros.append(f"{col} deve ser maior que zero: {_lista(pares)}.")

    # --- peso e volume -------------------------------------------------------------
    for col, unidade in (("peso_kg", "kg"), ("volume_l", "L")):
        ruins = produtos[produtos[col].notna() & (produtos[col] <= 0)]
        if len(ruins):
            erros.append(f"{col} deve ser maior que zero quando preenchido ({unidade}): "
                         f"{_lista(ruins['produto_id'])}.")

    # --- cidade e coordenadas ---------------------------------------------------
    fora = lojas[~lojas["cidade"].map(eh_ciudad_del_este)]
    if len(fora):
        erros.append("Somente lojas de Ciudad del Este são aceitas; fora da cidade: "
                     + _lista(f"{r.loja_id} ({r.cidade})" for r in fora.itertuples()) + ".")
    meia = lojas["latitude"].isna() ^ lojas["longitude"].isna()
    if meia.any():
        erros.append(f"Lojas com só latitude ou só longitude: {_lista(lojas.loc[meia, 'loja_id'])}.")
    com_coord = lojas["latitude"].notna() & lojas["longitude"].notna()
    fora_cde = lojas[com_coord & ~lojas.apply(lambda r: dentro_de_cde(r["latitude"], r["longitude"]), axis=1)]
    if len(fora_cde):
        erros.append("Coordenadas fora de Ciudad del Este: " + _lista(
            f"{r.loja_id} ({r.latitude}, {r.longitude})" for r in fora_cde.itertuples()) + ".")
    pendente_calculado = ~com_coord
    inconsistentes = lojas["coordenada_pendente"] != pendente_calculado
    if inconsistentes.any():
        alertas.append("coordenada_pendente corrigido conforme latitude/longitude em: "
                       f"{_lista(lojas.loc[inconsistentes, 'loja_id'])}.")
        lojas["coordenada_pendente"] = pendente_calculado

    # --- horários ------------------------------------------------------------------
    for r in lojas.itertuples():
        for col in ("abre", "fecha"):
            valor = getattr(r, col)
            if valor is not None and not _RE_HORA.match(valor):
                erros.append(f"Loja {r.loja_id}: '{col}' deve estar no formato HH:MM (recebido '{valor}').")
        if r.abre and r.fecha and _RE_HORA.match(r.abre) and _RE_HORA.match(r.fecha) and r.abre >= r.fecha:
            erros.append(f"Loja {r.loja_id}: horário de abertura ({r.abre}) deve ser anterior ao de fechamento ({r.fecha}).")
    tempo_ruim = lojas[lojas["tempo_permanencia_min"].notna() & (lojas["tempo_permanencia_min"] <= 0)]
    if len(tempo_ruim):
        erros.append(f"tempo_permanencia_min deve ser maior que zero: {_lista(tempo_ruim['loja_id'])}.")

    # --- datas de coleta ---------------------------------------------------------------
    datas = pd.to_datetime(ofertas["data_coleta"], format="%Y-%m-%d", errors="coerce")
    if datas.isna().any():
        erros.append("data_coleta ausente ou fora do formato AAAA-MM-DD em "
                     f"{int(datas.isna().sum())} oferta(s).")
    futuras = datas.dt.date > hoje
    if futuras.any():
        erros.append(f"{int(futuras.sum())} oferta(s) com data_coleta no futuro.")
    antigas = (datas.dt.date < hoje - dt.timedelta(days=dias_alerta)) & (ofertas["tipo_dado"] == "real")
    if antigas.any():
        alertas.append(f"{int(antigas.sum())} oferta(s) real(is) coletada(s) há mais de {dias_alerta} dias; "
                       "precisam ser recoletadas.")

    # --- lojas sem ofertas são descartadas ------------------------------------------
    sem_oferta = ~lojas["loja_id"].isin(ofertas["loja_id"])
    lojas_descartadas = [f"{r.loja_id} - {r.nome}" for r in lojas[sem_oferta].itertuples()]
    if lojas_descartadas:
        alertas.append(f"{len(lojas_descartadas)} loja(s) sem ofertas descartada(s): {_lista(lojas_descartadas)}.")
        lojas = lojas.loc[~sem_oferta].reset_index(drop=True)

    # --- todo produto tem oferta ------------------------------------------------------
    sem_oferta_p = produtos.loc[~produtos["produto_id"].isin(ofertas["produto_id"])]
    if len(sem_oferta_p):
        erros.append("Produtos sem nenhuma oferta: "
                     + _lista(f"{r.produto_id} ({r.nome})" for r in sem_oferta_p.itertuples()) + ".")

    return ResultadoValidacao(
        lojas=lojas, produtos=produtos, ofertas=ofertas, erros=erros, alertas=alertas,
        lojas_descartadas=lojas_descartadas, ofertas_sem_preco=ofertas_sem_preco,
    )
