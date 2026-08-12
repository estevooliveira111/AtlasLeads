# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

AtlasLeads is a Playwright-based scraper that pulls business listings (name,
address, website, phone, ratings, coordinates) from Google Maps searches, then
visits each business's website to harvest additional emails/phone numbers via
regex, and exports everything to CSV + XLSX. It's packaged as a standard
`src/`-layout Python package (`atlasleads`) with a console-script entrypoint.

## Setup and running

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

Run a single search:

```bash
atlasleads -s "Restaurantes em São Paulo" -t 50
# equivalent: python -m atlasleads -s "Restaurantes em São Paulo" -t 50
```

Run a batch from `input.txt` (one search term per line, e.g. `"Categoria em
Cidade"`; the file is gitignored, so create it locally) with parallel workers:

```bash
atlasleads -w 3
```

Enrich CSVs already collected under `output/` (visits each row's `website`
again without re-scraping Maps):

```bash
atlasleads --enrich-only
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
  `enrichment.scrape_contact_info` for each business's website.
- **`cli.py`** — argument parsing (`-s/--search`, `-t/--total`,
  `-w/--workers`, `--enrich-only`) and the `ProcessPoolExecutor` orchestration
  in `main()`. Registered as the `atlasleads` console script
  (`pyproject.toml` → `[project.scripts]`) and also runnable via
  `python -m atlasleads` (`__main__.py`).

## Core pipeline (per search query)

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
