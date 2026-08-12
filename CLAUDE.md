# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

AtlasLeads is a Playwright-based scraper that pulls business listings (name,
address, website, phone, ratings, coordinates) from Google Maps searches, then
visits each business's website to harvest additional emails/phone numbers via
regex, and exports everything to CSV + XLSX. It's a small, dependency-light
Python script project (no package structure, no tests, no CI).

## Setup and running

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

`requirements.txt` only lists `pandas`, `playwright`, and `openpyxl` — it is
missing `requests` and `beautifulsoup4`, both of which `emails.py` and
`atlas_leads.py` import for the contact-enrichment step. Install those
manually (`pip install requests beautifulsoup4`) when working on this repo,
and consider fixing `requirements.txt` if you touch that area.

Run a single search:

```bash
python3 main.py -s "Restaurantes em São Paulo" -t 50
# or the refactored entrypoint:
python3 atlas_leads.py -s "Imobiliária em São Paulo - SP" -t 50
```

Run a batch from `input.txt` (one search term per line, e.g. `"Categoria em
Cidade"`; the file is gitignored, so create it locally) with parallel workers:

```bash
python3 atlas_leads.py -w 3
```

Enrich CSVs already collected (visits each row's `website` again without
re-scraping Maps) — only available in `atlas_leads.py`:

```bash
python3 atlas_leads.py --enrich-only
```

Docker (uses `main.py`, headless by default via `ENV HEADLESS=true`):

```bash
docker build -t atlasleads .
docker run -it --rm -v "$(pwd)/AtlasLeads:/app/AtlasLeads" atlasleads -s "Imobiliaria em Guarulhos" -t 50
```

There are no tests, linter, or formatter configured in this repo.

## Architecture: two parallel implementations

This repo currently contains **two independent versions of the same
scraper**, not a single canonical pipeline:

- **`main.py` + `emails.py`** — the original implementation. `main.py`
  defines `Business`/`BusinessList`, drives Playwright, and calls
  `emails.scrape_site()` for contact enrichment. Output goes to
  `AtlasLeads/<YYYY-MM-DD>/`. This is what the `Dockerfile` runs.
- **`atlas_leads.py`** — a self-contained rewrite of the same logic (renamed
  `Business`/`BusinessCollection`, module-level `SELECTORS` dict, Portuguese
  docstrings, `--enrich-only` mode, graceful `Ctrl+C` shutdown that kills
  worker PIDs). Output goes to `atlas_leads/<YYYY-MM-DD>/` (lowercase,
  different directory than the legacy path). Not wired into the Dockerfile.

When fixing a bug or changing scraping behavior (selectors, dedup logic,
output format), check whether the change needs to be applied in **both**
`main.py`/`emails.py` and `atlas_leads.py` — they duplicate the same Google
Maps XPath selectors and regexes independently, so they can drift.

## Core pipeline (per search query)

1. **CLI/input parsing**: search term comes from `-s/--search`, or from
   `input.txt` (one query per line) when `-s` is omitted. `-t/--total` caps
   results per query (default effectively unlimited); `-w/--workers` sets how
   many queries run concurrently.
2. **Parallelism**: each search query runs in its own OS process via
   `concurrent.futures.ProcessPoolExecutor` (`process_search_query` /
   `scrape_query`), each launching its own Playwright/Chromium instance —
   queries do not share a browser. Within a single business's contact-page
   enrichment, a `ThreadPoolExecutor` (max 5 workers) fetches candidate
   contact pages concurrently.
3. **Google Maps scraping**: navigate to `google.com/maps`, dismiss the
   cookie-consent dialog, fill the search box, then scroll
   (`page.mouse.wheel`) in a loop until either `total` listings are found or
   the count stops increasing between scrolls (end of results). All Maps DOM
   lookups use XPath/CSS selectors hardcoded per field (name, address,
   website, phone, review count/average) — these are brittle and the most
   likely thing to need updating if Google changes its markup.
4. **Per-listing extraction**: click each listing, scrape the side panel
   fields into a `Business` dataclass, and parse lat/long out of the page URL
   (`/@lat,lon,...` segment).
5. **Contact enrichment**: if the business has an `http(s)` website, fetch it
   with `requests`, regex-extract emails/phones from the HTML, then follow
   any links whose href contains a contact-ish keyword (`contact`, `contato`,
   `about`, `phone`, `suporte`, `support`) up to `MAX_CONTACT_PAGES` (5) and
   merge in anything found there.
6. **Dedup**: `Business.__hash__` combines `name` with any of
   `domain`/`website`/`phone_number` that are present; `BusinessCollection`/
   `BusinessList` uses a `_seen` set to silently drop duplicates on `add()`.
7. **Persistence**: results are written as both `.csv` and `.xlsx` per search
   term (spaces replaced with `_`) into the date-stamped output directory. A
   query is skipped entirely on rerun if its output `.xlsx` already exists
   (resumability across runs, not per-row).

## Conventions

- User-facing `print()` output and most comments/docstrings are in
  Portuguese (pt-BR); the project targets Brazilian search queries and
  Playwright pages are created with `locale="pt-BR"`.
- `HEADLESS` env var (checked as `os.getenv('HEADLESS', 'false').lower() ==
  'true'`) controls whether Chromium runs headless; the Dockerfile sets it to
  `true`, local runs default to headed.
- Regexes for emails/phones (`EMAIL_REGEX`, `PHONE_REGEX`) are duplicated
  across `emails.py` and `atlas_leads.py`; the phone regex targets Brazilian
  number formats specifically.
