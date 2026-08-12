"""Interface de linha de comando: parsing de argumentos e orquestração dos comandos.

Três grupos de comandos:
  atlasleads scrape ...             coleta leads do Google Maps (comportamento padrão/legado)
  atlasleads locations states|cities  consulta estados/municípios e população (dados do IBGE)
  atlasleads queries build ...      combina cidades + palavras-chave em termos de busca
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys

from atlasleads import ibge
from atlasleads.constants import DATA_DIR, DEFAULT_TOTAL, INPUT_FILE
from atlasleads.enrichment import enrich_existing_csv_files
from atlasleads.maps_scraper import scrape_query
from atlasleads.query_builder import build_search_queries, parse_comma_list, write_queries

KNOWN_COMMANDS = ("scrape", "locations", "queries")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlasleads",
        description="AtlasLeads – Google Maps Lead Scraper",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    _add_scrape_subparser(subparsers)
    _add_locations_subparser(subparsers)
    _add_queries_subparser(subparsers)

    return parser


def _add_scrape_subparser(subparsers: argparse._SubParsersAction) -> None:
    scrape_parser = subparsers.add_parser(
        "scrape", help="Coleta leads do Google Maps (comportamento padrão)."
    )
    scrape_parser.add_argument(
        "-s", "--search",
        type=str, metavar="QUERY",
        help="Busca única (ex.: 'Imobiliária em São Paulo - SP').",
    )
    scrape_parser.add_argument(
        "-t", "--total",
        type=int, default=DEFAULT_TOTAL, metavar="N",
        help=f"Máximo de resultados por busca (padrão: {DEFAULT_TOTAL}).",
    )
    scrape_parser.add_argument(
        "-w", "--workers",
        type=int, default=1, metavar="N",
        help="Número de processos paralelos (padrão: 1).",
    )
    scrape_parser.add_argument(
        "--enrich-only",
        action="store_true",
        help=f"Apenas enriquece CSVs existentes em '{DATA_DIR}', sem nova coleta.",
    )


def _add_locations_subparser(subparsers: argparse._SubParsersAction) -> None:
    locations_parser = subparsers.add_parser(
        "locations", help="Consulta estados e municípios (dados do IBGE)."
    )
    locations_sub = locations_parser.add_subparsers(dest="locations_command", required=True)

    states_parser = locations_sub.add_parser("states", help="Lista os estados brasileiros.")
    states_parser.add_argument("--json", action="store_true", help="Imprime em formato JSON.")
    states_parser.add_argument(
        "--no-cache", action="store_true", help="Ignora o cache local e busca dados atualizados."
    )

    cities_parser = locations_sub.add_parser(
        "cities", help="Lista os municípios de uma UF, com população estimada."
    )
    cities_parser.add_argument(
        "--uf", required=True, metavar="UF", help="Sigla do estado (ex.: SP)."
    )
    cities_parser.add_argument(
        "--min-population", type=int, default=None, metavar="N",
        help="Filtra municípios com população estimada >= N.",
    )
    cities_parser.add_argument(
        "--sort", choices=["nome", "populacao"], default="nome",
        help="Critério de ordenação (padrão: nome).",
    )
    cities_parser.add_argument(
        "--limit", type=int, default=None, metavar="N", help="Limita a N resultados."
    )
    cities_parser.add_argument("--json", action="store_true", help="Imprime em formato JSON.")
    cities_parser.add_argument(
        "--no-cache", action="store_true", help="Ignora o cache local e busca dados atualizados."
    )


def _add_queries_subparser(subparsers: argparse._SubParsersAction) -> None:
    queries_parser = subparsers.add_parser(
        "queries", help="Monta termos de busca combinando cidades + palavras-chave."
    )
    queries_sub = queries_parser.add_subparsers(dest="queries_command", required=True)

    build_parser = queries_sub.add_parser(
        "build", help="Combina cidades (IBGE) e palavras-chave em termos de busca."
    )
    build_parser.add_argument(
        "--uf", required=True, metavar="UF", help="Sigla do estado (ex.: SP)."
    )
    build_parser.add_argument(
        "--keywords", required=True, metavar="LISTA",
        help="Palavras-chave separadas por vírgula (ex.: 'restaurante,padaria').",
    )
    build_parser.add_argument(
        "--cities", default=None, metavar="LISTA",
        help="Nomes de cidades separados por vírgula. Se omitido, usa todas as cidades da UF "
        "(respeitando --min-population, se informado).",
    )
    build_parser.add_argument(
        "--min-population", type=int, default=None, metavar="N",
        help="Considera apenas municípios com população estimada >= N.",
    )
    build_parser.add_argument(
        "--output", default=INPUT_FILE, metavar="ARQUIVO",
        help=f"Arquivo de saída (padrão: '{INPUT_FILE}').",
    )
    build_parser.add_argument(
        "--append", action="store_true",
        help="Preserva o conteúdo existente do arquivo e apenas adiciona termos novos "
        "(padrão: sobrescreve com a lista gerada).",
    )
    build_parser.add_argument(
        "--dry-run", action="store_true",
        help="Apenas mostra os termos gerados, sem gravar em disco.",
    )
    build_parser.add_argument(
        "--no-cache", action="store_true", help="Ignora o cache local e busca dados atualizados."
    )


def _normalize_argv(argv: list[str]) -> list[str]:
    """Permite `atlasleads -s ...` como atalho retrocompatível para `atlasleads scrape -s ...`."""
    if not argv:
        return ["scrape"]
    if argv[0] not in KNOWN_COMMANDS and argv[0] not in ("-h", "--help"):
        return ["scrape", *argv]
    return argv


def _load_search_list(search_arg: str | None) -> list[str]:
    """Retorna a lista de buscas a partir do argumento CLI ou do arquivo de entrada."""
    if search_arg:
        return [search_arg]

    if not os.path.exists(INPUT_FILE):
        print(f"Erro: arquivo '{INPUT_FILE}' não encontrado e argumento -s não fornecido.")
        sys.exit(1)

    with open(INPUT_FILE, encoding="utf-8") as f:
        searches = [line.strip() for line in f if line.strip()]

    if not searches:
        print(f"Erro: '{INPUT_FILE}' está vazio. Adicione buscas ou use -s.")
        sys.exit(1)

    return searches


def _run_scrape(args: argparse.Namespace) -> None:
    if args.enrich_only:
        print(f"Modo de enriquecimento: processando CSVs em '{DATA_DIR}'...")
        enrich_existing_csv_files()
        return

    search_list = _load_search_list(args.search)
    print(
        f"Iniciando raspagem: {len(search_list)} busca(s) | "
        f"{args.workers} worker(s) | máximo {args.total} resultado(s) por busca."
    )

    pool = concurrent.futures.ProcessPoolExecutor(max_workers=args.workers)
    try:
        futures = {
            pool.submit(scrape_query, idx, query, args.total): query
            for idx, query in enumerate(search_list)
        }
        for future in concurrent.futures.as_completed(futures):
            query = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f"Worker falhou para '{query}': {exc}")
    except KeyboardInterrupt:
        print("\n[!] Interrupção forçada detectada (Ctrl+C). Encerrando robôs...")
        for pid in pool._processes:
            try:
                os.kill(pid, 9)
            except Exception:
                pass
        os._exit(1)
    finally:
        pool.shutdown(wait=True)


def _format_population(populacao: int | None) -> str:
    return f"{populacao:,}".replace(",", ".") if populacao is not None else "N/D"


def _run_locations_states(args: argparse.Namespace) -> None:
    try:
        states = ibge.list_states(use_cache=not args.no_cache)
    except ibge.IBGEAPIError as exc:
        print(f"Erro ao consultar a API do IBGE: {exc}")
        sys.exit(1)

    if args.json:
        print(json.dumps([s.__dict__ for s in states], ensure_ascii=False, indent=2))
        return

    for state in states:
        print(f"{state.sigla}\t{state.nome}\t{state.regiao}")


def _run_locations_cities(args: argparse.Namespace) -> None:
    try:
        cities = ibge.list_municipalities_with_population(args.uf, use_cache=not args.no_cache)
    except (ibge.IBGEAPIError, ValueError) as exc:
        print(f"Erro ao consultar a API do IBGE: {exc}")
        sys.exit(1)

    if args.min_population is not None:
        cities = [c for c in cities if (c.populacao or 0) >= args.min_population]

    if args.sort == "populacao":
        cities.sort(key=lambda c: c.populacao or 0, reverse=True)

    if args.limit is not None:
        cities = cities[: args.limit]

    if args.json:
        print(json.dumps([c.__dict__ for c in cities], ensure_ascii=False, indent=2))
        return

    print(f"{len(cities)} município(s) em {args.uf.upper()}:")
    for city in cities:
        print(f"  {city.nome} - {city.uf_sigla}\tpopulação: {_format_population(city.populacao)}")


def _run_locations(args: argparse.Namespace) -> None:
    if args.locations_command == "states":
        _run_locations_states(args)
    elif args.locations_command == "cities":
        _run_locations_cities(args)


def _select_cities(args: argparse.Namespace) -> list[ibge.Municipality]:
    all_cities = ibge.list_municipalities_with_population(args.uf, use_cache=not args.no_cache)
    if args.min_population is not None:
        all_cities = [c for c in all_cities if (c.populacao or 0) >= args.min_population]

    if not args.cities:
        return all_cities

    requested = parse_comma_list(args.cities)
    by_normalized_name = {ibge.normalize_name(c.nome): c for c in all_cities}

    selected = []
    for name in requested:
        match = by_normalized_name.get(ibge.normalize_name(name))
        if match:
            selected.append(match)
        else:
            print(
                f"Aviso: cidade '{name}' não encontrada em {args.uf.upper()} "
                "(ou não atende ao --min-population)."
            )
    return selected


def _run_queries_build(args: argparse.Namespace) -> None:
    keywords = parse_comma_list(args.keywords)
    if not keywords:
        print("Erro: informe ao menos uma palavra-chave em --keywords.")
        sys.exit(1)

    try:
        cities = _select_cities(args)
    except (ibge.IBGEAPIError, ValueError) as exc:
        print(f"Erro ao consultar a API do IBGE: {exc}")
        sys.exit(1)

    if not cities:
        print("Nenhuma cidade selecionada. Nada a fazer.")
        sys.exit(1)

    queries = build_search_queries(
        cities=[c.nome for c in cities], keywords=keywords, uf=args.uf
    )
    print(f"{len(queries)} termo(s) de busca gerado(s) a partir de {len(cities)} cidade(s).")

    if args.dry_run:
        for query in queries:
            print(query)
        return

    added = write_queries(queries, output_path=args.output, append=args.append)
    action = "adicionado(s) a" if args.append else "gravado(s) em"
    print(f"{added} termo(s) novo(s) {action} '{args.output}'.")


def _run_queries(args: argparse.Namespace) -> None:
    if args.queries_command == "build":
        _run_queries_build(args)


def main() -> None:
    """Ponto de entrada principal da aplicação."""
    parser = _build_arg_parser()
    args = parser.parse_args(_normalize_argv(sys.argv[1:]))

    if args.command == "scrape":
        _run_scrape(args)
    elif args.command == "locations":
        _run_locations(args)
    elif args.command == "queries":
        _run_queries(args)
    else:
        parser.print_help()
