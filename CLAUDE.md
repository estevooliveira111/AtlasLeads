# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

AtlasLeads is a Playwright-based scraper that pulls business listings (name,
address, website, phone, ratings, coordinates) from Google Maps searches, then
visits each business's website to harvest additional emails/phone numbers via
regex, and exports everything to CSV + XLSX. It also includes an IBGE API
client (states/municipalities/population) and a query builder that combines
chosen cities with chosen keywords into ready-to-scrape search terms. It's
packaged as a standard `src/`-layout Python package (`atlasleads`) with a
console-script entrypoint.

## Setup and running

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

The CLI has three subcommands: `scrape` (the original scraper), `locations`
(IBGE lookups), and `queries` (build search terms). `scrape` has a
backward-compatible shortcut: `atlasleads -s ...` is rewritten to
`atlasleads scrape -s ...` by `cli._normalize_argv()` when the first token
isn't a known subcommand, so old-style invocations still work.

Run a single search:

```bash
atlasleads scrape -s "Restaurantes em São Paulo" -t 50
# legacy shortcut, still supported: atlasleads -s "Restaurantes em São Paulo" -t 50
```

Run a batch from `input.txt` (one search term per line, e.g. `"Categoria em
Cidade - UF"`; the file is gitignored, so create it locally, or generate it
with `queries build` below) with parallel workers:

```bash
atlasleads scrape -w 3
```

Enrich CSVs already collected under `output/` (visits each row's `website`
again without re-scraping Maps):

```bash
atlasleads scrape --enrich-only
```

Look up IBGE data (states, or municipalities of a UF with estimated
population; results are disk-cached under `output/.cache/` for 7 days):

```bash
atlasleads locations states
atlasleads locations cities --uf SP --sort populacao --limit 20
```

Generate `input.txt` search terms by combining chosen cities with chosen
keywords (validated against the IBGE municipality list; omit `--cities` to
use every city in the UF, optionally filtered by `--min-population`):

```bash
atlasleads queries build --uf SP --cities "São Paulo, Campinas" --keywords "restaurante, padaria"
atlasleads queries build --uf SP --min-population 200000 --keywords "clínica odontológica" --dry-run
```

Run tests / lint:

```bash
pytest
ruff check .
```

Docker (headless by default via `ENV HEADLESS=true`, entrypoint is the
`atlasleads` console script):

```bash
docker build -t atlasleads .
docker run -it --rm -v "$(pwd)/output:/app/output" atlasleads -s "Imobiliaria em Guarulhos" -t 50
```

## Package layout (`src/atlasleads/`)

- **`constants.py`** — `DATA_DIR` (`output/`), `INPUT_FILE`, HTTP
  headers/timeout, `EMAIL_REGEX`/`PHONE_REGEX`, and the `SELECTORS` dict of
  Google Maps XPath/CSS selectors. This is the first place to look (and the
  most likely thing to need updating) if Google changes its markup.
- **`models.py`** — `Business` (one lead) and `BusinessCollection`
  (dedup + save-to-CSV/XLSX). `Business.__hash__` combines `name` with
  whichever of `domain`/`website`/`phone_number` are present;
  `BusinessCollection.add()` silently drops duplicates via a `_seen` set of
  hashes.
- **`enrichment.py`** — pure HTTP/regex contact-enrichment logic
  (`scrape_contact_info`, `enrich_existing_csv_files`). No Playwright
  dependency, so this is the easiest module to unit test.
- **`maps_scraper.py`** — Playwright-driven Google Maps scraping
  (`scrape_query` is the per-search-term entrypoint), calling into
  `enrichment.scrape_contact_info` for each business's website. Splits each
  search query on `" em "` to derive `Business.category`/`.location` — the
  query format everywhere in this codebase is
  `"<keyword> em <City> - <UF>"` (Portuguese), not English `" in "`.
- **`ibge.py`** — client for the public IBGE APIs: `list_states()` /
  `list_municipalities(uf)` hit the Localidades API
  (`servicodados.ibge.gov.br/api/v1/localidades`), and
  `fetch_population_by_uf(uf)` hits the SIDRA Agregados API (aggregate 6579,
  variable 9324 = "população residente estimada") to get each municipality's
  latest population estimate. `list_municipalities_with_population(uf)`
  merges the two and is the main entrypoint other modules should call.
  Responses are cached as JSON under `output/.cache/` for `CACHE_TTL_SECONDS`
  (1 week) via `_read_cache`/`_write_cache`; pass `use_cache=False` to bypass.
  Population lookup failures are swallowed (population stays `None`) so a
  flaky/changed IBGE endpoint never blocks getting the city list itself.
- **`query_builder.py`** — `build_search_queries(cities, keywords, uf)`
  produces the cartesian product of keywords × cities as
  `"<keyword> em <city> - <UF>"` strings (must stay in sync with the `" em "`
  split in `maps_scraper.py`); `write_queries()` appends/overwrites them into
  a file like `input.txt`, deduplicating against existing lines.
- **`cli.py`** — argparse with three subcommands: `scrape` (original
  flags: `-s/--search`, `-t/--total`, `-w/--workers`, `--enrich-only`),
  `locations states|cities` (prints/JSON-dumps IBGE data), and
  `queries build` (resolves `--cities`/`--min-population` against
  `ibge.list_municipalities_with_population()`, matching city names
  accent/case-insensitively via `ibge.normalize_name()`, then calls
  `query_builder` and writes/prints the result). `_normalize_argv()`
  prepends `"scrape"` when the first CLI token isn't a known subcommand, for
  backward compatibility. Registered as the `atlasleads` console script
  (`pyproject.toml` → `[project.scripts]`) and also runnable via
  `python -m atlasleads` (`__main__.py`).

## Core pipeline (per search query)

Typical end-to-end flow: `atlasleads queries build ...` generates
`input.txt` from IBGE city data + chosen keywords, then
`atlasleads scrape -w N` reads it and runs the pipeline below per line.

1. **CLI/input parsing**: search term comes from `-s/--search`, or from
   `input.txt` (one query per line) when `-s` is omitted. `-t/--total` caps
   results per query (default effectively unlimited); `-w/--workers` sets how
   many queries run concurrently.
2. **Parallelism**: each search query runs in its own OS process via
   `concurrent.futures.ProcessPoolExecutor` (`cli.main` → `maps_scraper.scrape_query`),
   each launching its own Playwright/Chromium instance — queries do not share
   a browser. Within a single business's contact-page enrichment, a
   `ThreadPoolExecutor` (max 5 workers, `MAX_CONTACT_PAGES`) fetches
   candidate contact pages concurrently.
3. **Google Maps scraping**: navigate to `google.com/maps`, dismiss the
   cookie-consent dialog, fill the search box, then scroll
   (`page.mouse.wheel`) in a loop until either `total` listings are found or
   the count stops increasing between scrolls (end of results).
4. **Per-listing extraction**: click each listing, scrape the side panel
   fields into a `Business` dataclass, and parse lat/long out of the page URL
   (`/@lat,lon,...` segment via `_parse_coordinates`).
5. **Contact enrichment**: if the business has an `http(s)` website, fetch it
   with `requests`, regex-extract emails/phones from the HTML, then follow
   any links whose href contains a contact-ish keyword (`contact`, `contato`,
   `about`, `phone`, `suporte`, `support`) up to `MAX_CONTACT_PAGES` and merge
   in anything found there.
6. **Dedup**: see `Business.__hash__` / `BusinessCollection.add()` above.
7. **Persistence**: results are written as both `.csv` and `.xlsx` per search
   term (spaces replaced with `_`) into `output/<YYYY-MM-DD>/`. A query is
   skipped entirely on rerun if its output `.xlsx` already exists
   (resumability across runs, not per-row).

## Conventions

- User-facing `print()` output and most comments/docstrings are in
  Portuguese (pt-BR); the project targets Brazilian search queries and
  Playwright pages are created with `locale="pt-BR"`.
- `HEADLESS` env var (checked as `os.getenv('HEADLESS', 'false').lower() ==
  'true'`) controls whether Chromium runs headless; the Dockerfile sets it to
  `true`, local runs default to headed.
- `PHONE_REGEX` targets Brazilian phone number formats specifically.
- Dependencies and their pinned versions live in `pyproject.toml`
  (`[project.dependencies]` / `[project.optional-dependencies].dev`) — there
  is no separate `requirements.txt`.
