"""Interface de linha de comando: parsing de argumentos e orquestração dos workers."""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import sys

from atlasleads.constants import DATA_DIR, DEFAULT_TOTAL, INPUT_FILE
from atlasleads.enrichment import enrich_existing_csv_files
from atlasleads.maps_scraper import scrape_query


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlasleads",
        description="AtlasLeads – Google Maps Lead Scraper",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-s", "--search",
        type=str, metavar="QUERY",
        help="Busca única (ex.: 'Imobiliária em São Paulo - SP').",
    )
    parser.add_argument(
        "-t", "--total",
        type=int, default=DEFAULT_TOTAL, metavar="N",
        help=f"Máximo de resultados por busca (padrão: {DEFAULT_TOTAL}).",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int, default=1, metavar="N",
        help="Número de processos paralelos (padrão: 1).",
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help=f"Apenas enriquece CSVs existentes em '{DATA_DIR}', sem nova coleta.",
    )
    return parser


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


def main() -> None:
    """Ponto de entrada principal da aplicação."""
    parser = _build_arg_parser()
    args = parser.parse_args()

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
