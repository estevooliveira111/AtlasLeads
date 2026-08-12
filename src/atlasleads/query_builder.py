"""Combina cidades (dados do IBGE) e palavras-chave em termos de busca para o scraper."""

from __future__ import annotations

import os


def parse_comma_list(raw: str) -> list[str]:
    """Divide uma string separada por vírgulas em itens não vazios e sem espaços extras."""
    return [item.strip() for item in raw.split(",") if item.strip()]


def build_search_queries(
    cities: list[str], keywords: list[str], uf: str | None = None
) -> list[str]:
    """
    Gera um termo de busca para cada combinação de palavra-chave x cidade,
    no formato usado pelo scraper: "<palavra-chave> em <Cidade>[ - UF]".

    Args:
        cities: nomes de cidades (ex.: ["São Paulo", "Campinas"]).
        keywords: palavras-chave/categorias (ex.: ["restaurante", "padaria"]).
        uf: sigla do estado, anexada ao nome da cidade quando informada.

    Returns:
        Lista de termos de busca, palavra-chave por palavra-chave, cidade por cidade.
    """
    uf_suffix = f" - {uf.strip().upper()}" if uf else ""
    queries: list[str] = []
    for keyword in keywords:
        keyword = keyword.strip()
        if not keyword:
            continue
        for city in cities:
            city = city.strip()
            if not city:
                continue
            queries.append(f"{keyword} em {city}{uf_suffix}")
    return queries


def write_queries(queries: list[str], output_path: str, append: bool) -> int:
    """
    Persiste os termos de busca em `output_path` (uma por linha), deduplicando
    contra o que já existir no arquivo.

    Args:
        queries: termos de busca a gravar.
        output_path: caminho do arquivo (ex.: 'input.txt').
        append: se True, preserva o conteúdo existente e só adiciona termos novos;
            se False, sobrescreve o arquivo com a lista deduplicada de `queries`.

    Returns:
        Número de linhas novas efetivamente adicionadas ao arquivo.
    """
    existing: list[str] = []
    if append and os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            existing = [line.strip() for line in f if line.strip()]

    seen = set(existing)
    new_lines = []
    for query in queries:
        if query not in seen:
            seen.add(query)
            new_lines.append(query)

    with open(output_path, "w", encoding="utf-8") as f:
        for line in [*existing, *new_lines]:
            f.write(f"{line}\n")

    return len(new_lines)
