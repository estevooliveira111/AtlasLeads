"""Cliente para a API pública do IBGE: estados, municípios e população estimada.

Usa a API de Localidades (https://servicodados.ibge.gov.br/api/docs/localidades)
para estados/municípios e a API de Agregados/SIDRA
(https://servicodados.ibge.gov.br/api/docs/agregados) para a estimativa de
população residente por município (agregado 6579, variável 9324).

Respostas são cacheadas em disco por `CACHE_TTL_SECONDS`, já que dados
geográficos e estimativas populacionais do IBGE mudam raramente.
"""

from __future__ import annotations

import json
import os
import time
import unicodedata
from dataclasses import dataclass, field

import requests

LOCALIDADES_BASE_URL = "https://servicodados.ibge.gov.br/api/v1/localidades"
AGREGADOS_BASE_URL = "https://servicodados.ibge.gov.br/api/v3/agregados"

# Agregado 6579 = "População residente estimada", variável 9324.
POPULATION_AGGREGATE_ID = 6579
POPULATION_VARIABLE_ID = 9324

CACHE_DIR = os.path.join("output", ".cache")
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 1 semana
HTTP_TIMEOUT = 20


class IBGEAPIError(RuntimeError):
    """Erro ao consultar a API do IBGE."""


@dataclass(frozen=True)
class State:
    """Um estado (UF) brasileiro."""

    id: int
    sigla: str
    nome: str
    regiao: str


@dataclass
class Municipality:
    """Um município brasileiro, com população estimada quando disponível."""

    id: int
    nome: str
    uf_sigla: str
    uf_nome: str
    populacao: int | None = field(default=None)


def normalize_name(name: str) -> str:
    """Normaliza um nome para comparação: remove acentos, espaços extras e caixa."""
    decomposed = unicodedata.normalize("NFKD", name)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.strip().lower().split())


def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def _read_cache(key: str):
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    if time.time() - os.path.getmtime(path) > CACHE_TTL_SECONDS:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(key: str, data) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(_cache_path(key), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def _get_json(url: str, params: dict | None = None):
    try:
        response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise IBGEAPIError(f"Falha ao consultar {url}: {exc}") from exc
    try:
        return response.json()
    except ValueError as exc:
        raise IBGEAPIError(f"Resposta inválida (não é JSON) de {url}") from exc


def list_states(use_cache: bool = True) -> list[State]:
    """Lista os 26 estados + Distrito Federal, ordenados por nome."""
    cache_key = "estados"
    if use_cache:
        cached = _read_cache(cache_key)
        if cached is not None:
            return [State(**s) for s in cached]

    data = _get_json(f"{LOCALIDADES_BASE_URL}/estados", params={"orderBy": "nome"})
    states = [
        State(
            id=item["id"],
            sigla=item["sigla"],
            nome=item["nome"],
            regiao=item.get("regiao", {}).get("nome", ""),
        )
        for item in data
    ]
    _write_cache(cache_key, [s.__dict__ for s in states])
    return states


def get_state_by_sigla(uf: str, states: list[State] | None = None) -> State:
    """Busca um estado pela sigla (ex.: 'SP'). Lança ValueError se não existir."""
    states = states if states is not None else list_states()
    uf_upper = uf.strip().upper()
    for state in states:
        if state.sigla == uf_upper:
            return state
    raise ValueError(f"UF desconhecida: '{uf}'")


def list_municipalities(uf: str, use_cache: bool = True) -> list[Municipality]:
    """Lista os municípios de uma UF (sem população), ordenados por nome."""
    uf_upper = uf.strip().upper()
    cache_key = f"municipios_{uf_upper}"
    if use_cache:
        cached = _read_cache(cache_key)
        if cached is not None:
            return [Municipality(**m) for m in cached]

    data = _get_json(f"{LOCALIDADES_BASE_URL}/estados/{uf_upper}/municipios")
    municipalities = sorted(
        (_parse_municipality(item, uf_upper) for item in data),
        key=lambda m: m.nome,
    )
    _write_cache(cache_key, [m.__dict__ for m in municipalities])
    return municipalities


def _parse_municipality(item: dict, uf_upper: str) -> Municipality:
    """Extrai um Municipality de um item bruto da API de localidades."""
    uf_info = (
        item.get("microrregiao", {}).get("mesorregiao", {}).get("UF")
        or item.get("regiao-imediata", {}).get("regiao-intermediaria", {}).get("UF")
        or {}
    )
    return Municipality(
        id=item["id"],
        nome=item["nome"],
        uf_sigla=uf_info.get("sigla", uf_upper),
        uf_nome=uf_info.get("nome", ""),
    )


def fetch_population_by_uf(uf: str, use_cache: bool = True) -> dict[int, int]:
    """Retorna {municipio_id: população estimada} para a UF (última estimativa disponível)."""
    uf_upper = uf.strip().upper()
    cache_key = f"populacao_{uf_upper}"
    if use_cache:
        cached = _read_cache(cache_key)
        if cached is not None:
            return {int(k): v for k, v in cached.items()}

    state = get_state_by_sigla(uf_upper)
    url = (
        f"{AGREGADOS_BASE_URL}/{POPULATION_AGGREGATE_ID}"
        f"/periodos/-1/variaveis/{POPULATION_VARIABLE_ID}"
    )
    data = _get_json(url, params={"localidades": f"N6[N3[{state.id}]]"})

    population: dict[int, int] = {}
    for variable in data:
        for resultado in variable.get("resultados", []):
            for serie in resultado.get("series", []):
                try:
                    localidade_id = int(serie["localidade"]["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                valores = [
                    v for v in serie.get("serie", {}).values() if v not in (None, "-", "...", "")
                ]
                if not valores:
                    continue
                try:
                    population[localidade_id] = int(valores[-1])
                except (TypeError, ValueError):
                    continue

    _write_cache(cache_key, population)
    return population


def list_municipalities_with_population(uf: str, use_cache: bool = True) -> list[Municipality]:
    """Lista os municípios de uma UF com a população estimada preenchida quando disponível."""
    municipalities = list_municipalities(uf, use_cache=use_cache)
    try:
        population = fetch_population_by_uf(uf, use_cache=use_cache)
    except IBGEAPIError:
        population = {}
    for municipality in municipalities:
        municipality.populacao = population.get(municipality.id)
    return municipalities
