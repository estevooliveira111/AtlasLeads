"""
AtlasLeads – Google Maps Lead Scraper
======================================
Raspa leads do Google Maps (nome, endereço, site, telefone, avaliações),
visita o site de cada empresa para extrair e-mails e telefones extras e
salva os resultados em CSV e XLSX.

Uso
---
    # Busca única:
    python atlas_leads.py -s "Imobiliária em São Paulo - SP"

    # Lê input.txt (uma busca por linha) com 3 workers paralelos:
    python atlas_leads.py -w 3

    # Limitar a 50 resultados por busca:
    python atlas_leads.py -t 50 -w 2

    # Enriquecer CSVs já existentes (sem nova coleta no Maps):
    python atlas_leads.py --enrich-only
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Imports – stdlib
# ---------------------------------------------------------------------------
import argparse
import concurrent.futures
import csv
import datetime
import glob
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Imports – third-party
# ---------------------------------------------------------------------------
import pandas as pd
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DATA_DIR: str = "atlas_leads"
INPUT_FILE: str = "input.txt"
DEFAULT_TOTAL: int = 1_000_000
MAX_CONTACT_PAGES: int = 5

CONTACT_KEYWORDS: tuple[str, ...] = (
    "contact", "contato", "about", "phone", "suporte", "support",
)

HTTP_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8,en-US;q=0.6",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

HTTP_TIMEOUT: int = 10

EMAIL_REGEX: re.Pattern[str] = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)
PHONE_REGEX: re.Pattern[str] = re.compile(
    r"(?:\+?55\s?)?\(?\b[1-9]{2}\)?\s?(?:9\s?\d{4}|\d{4})[-.\s]?\d{4}\b"
)

SELECTORS: dict[str, str] = {
    "name": "h1.DUwDvf",
    "address": '//button[@data-item-id="address"]//div[contains(@class,"fontBodyMedium")]',
    "website": '//a[@data-item-id="authority"]//div[contains(@class,"fontBodyMedium")]',
    "phone": '//button[contains(@data-item-id,"phone:tel:")]//div[contains(@class,"fontBodyMedium")]',
    "reviews_count": '//div[@jsaction="pane.reviewChart.moreReviews"]//span',
    "reviews_avg": '//div[@jsaction="pane.reviewChart.moreReviews"]//div[@role="img"]',
    "listing": '//a[contains(@href,"https://www.google.com/maps/place")]',
    "consent": (
        'button[aria-label="Accept all"],'
        'button[aria-label="Agree"],'
        'button[aria-label="Aceitar tudo"],'
        'button[aria-label="Concordo"],'
        'button:has-text("Accept all"),'
        'button:has-text("Aceitar tudo")'
    ),
    "search_box": 'input#searchboxinput, input[name="q"], input[role="combobox"]',
}

# ---------------------------------------------------------------------------
# Modelos de dados
# ---------------------------------------------------------------------------


@dataclass
class Business:
    """Representa os dados de um lead coletado do Google Maps."""

    name: Optional[str] = None
    address: Optional[str] = None
    domain: Optional[str] = None
    website: Optional[str] = None
    phone_number: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    reviews_count: Optional[int] = None
    reviews_average: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    emails: Optional[str] = None
    scraped_phones: Optional[str] = None

    def __hash__(self) -> int:
        """Gera hash com base em nome + campos de contato não-vazios."""
        key_parts = [self.name]
        if self.domain:
            key_parts.append(f"domain:{self.domain}")
        if self.website:
            key_parts.append(f"website:{self.website}")
        if self.phone_number:
            key_parts.append(f"phone:{self.phone_number}")
        return hash(tuple(key_parts))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Business) and hash(self) == hash(other)


@dataclass
class BusinessCollection:
    """Coleção de leads com deduplicação automática e persistência em CSV/XLSX."""

    _items: list[Business] = field(default_factory=list, init=False)
    _seen: set[int] = field(default_factory=set, init=False)
    _output_dir: str = field(init=False)

    def __post_init__(self) -> None:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self._output_dir = os.path.join(DATA_DIR, today)
        os.makedirs(self._output_dir, exist_ok=True)

    def add(self, business: Business) -> None:
        """Adiciona um lead ao conjunto se ainda não existir."""
        key = hash(business)
        if key not in self._seen:
            self._items.append(business)
            self._seen.add(key)

    def to_dataframe(self) -> pd.DataFrame:
        """Converte a coleção em um DataFrame pandas."""
        return pd.json_normalize(
            (asdict(b) for b in self._items), sep="_"
        )

    def save(self, filename: str) -> None:
        """Persiste a coleção em CSV e XLSX no diretório de saída."""
        safe_name = filename.replace(" ", "_")
        df = self.to_dataframe()
        df.to_csv(os.path.join(self._output_dir, f"{safe_name}.csv"), index=False)
        df.to_excel(os.path.join(self._output_dir, f"{safe_name}.xlsx"), index=False)

    @property
    def output_dir(self) -> str:
        return self._output_dir

    def __len__(self) -> int:
        return len(self._items)


# ---------------------------------------------------------------------------
# Serviço de enriquecimento de contatos (HTTP scraping)
# ---------------------------------------------------------------------------


def _fetch_html(url: str) -> str:
    """Realiza requisição GET e retorna o HTML ou string vazia em caso de erro."""
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS)
        return response.text if response.status_code == 200 else ""
    except requests.RequestException:
        return ""


def _extract_emails(text: str) -> set[str]:
    """Extrai todos os endereços de e-mail únicos do texto."""
    return set(EMAIL_REGEX.findall(text))


def _extract_phones(text: str) -> set[str]:
    """Extrai todos os números de telefone brasileiros únicos do texto."""
    return set(PHONE_REGEX.findall(text))


def _fetch_and_extract(url: str) -> tuple[set[str], set[str]]:
    """Busca uma URL e retorna (emails, telefones) encontrados no conteúdo."""
    html = _fetch_html(url)
    return _extract_emails(html), _extract_phones(html)


def scrape_contact_info(base_url: str) -> tuple[set[str], set[str]]:
    """
    Extrai e-mails e telefones de um site.

    Visita a página principal e, em paralelo, até MAX_CONTACT_PAGES
    sub-páginas identificadas por palavras-chave de contato.

    Args:
        base_url: URL principal do site da empresa.

    Returns:
        Tupla (emails, telefones) como conjuntos de strings.
    """
    emails: set[str] = set()
    phones: set[str] = set()

    html = _fetch_html(base_url)
    if not html:
        return emails, phones

    emails |= _extract_emails(html)
    phones |= _extract_phones(html)

    soup = BeautifulSoup(html, "html.parser")
    contact_links = [
        urljoin(base_url, a.get("href", ""))
        for a in soup.select("a[href]")
        if any(kw in (a.get("href") or "").lower() for kw in CONTACT_KEYWORDS)
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONTACT_PAGES) as pool:
        futures = [
            pool.submit(_fetch_and_extract, link)
            for link in contact_links[:MAX_CONTACT_PAGES]
        ]
        for future in concurrent.futures.as_completed(futures):
            try:
                em, ph = future.result()
                emails |= em
                phones |= ph
            except Exception:
                pass

    return emails, phones


# ---------------------------------------------------------------------------
# Serviço de enriquecimento de CSVs existentes
# ---------------------------------------------------------------------------


def enrich_existing_csv_files(data_dir: str = DATA_DIR) -> None:
    """
    Percorre todos os CSVs dentro de `data_dir` e preenche as colunas
    `emails` e `scraped_phones` para linhas que ainda não foram processadas.
    """
    csv_paths = glob.glob(os.path.join(data_dir, "**/*.csv"), recursive=True)
    for file_path in csv_paths:
        print(f"\nProcessando: {file_path}")
        _enrich_single_csv(file_path)


def _enrich_single_csv(file_path: str) -> None:
    """Abre, enriquece e salva um único arquivo CSV."""
    with open(file_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return

        fieldnames = list(reader.fieldnames)
        for col in ("emails", "scraped_phones"):
            if col not in fieldnames:
                fieldnames.append(col)

        rows = list(reader)

    modified = False
    for row in rows:
        website = row.get("website", "")
        already_enriched = row.get("emails") and row.get("scraped_phones")

        if website and website.startswith("http") and not already_enriched:
            print(f"  Scraping {website}...", end=" ", flush=True)
            emails, phones = scrape_contact_info(website)

            email_log = f"Email: {', '.join(emails)}" if emails else "Email: Não achou"
            phone_log = f"Telefone: {', '.join(phones)}" if phones else "Telefone: Não achou"
            print(f"-> {email_log} | {phone_log}")

            row["emails"] = ", ".join(emails)
            row["scraped_phones"] = ", ".join(phones)
            modified = True
        else:
            row.setdefault("emails", "")
            row.setdefault("scraped_phones", "")

    if modified:
        with open(file_path, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


# ---------------------------------------------------------------------------
# Scraper do Google Maps (Playwright)
# ---------------------------------------------------------------------------


def _accept_cookie_consent(page: Page) -> None:
    """Fecha o modal de consentimento de cookies do Google, se presente."""
    try:
        consent = page.locator(SELECTORS["consent"])
        if consent.count() > 0:
            consent.first.click()
            page.wait_for_timeout(2000)
    except Exception:
        pass


def _scroll_until_loaded(page: Page, max_results: int, label: str) -> list:
    """
    Rola a lista de resultados do Maps até atingir `max_results` ou o fim.

    Returns:
        Lista de elementos Playwright representando cards de empresa.
    """
    listing_sel = SELECTORS["listing"]
    previously_counted = 0

    while True:
        page.mouse.wheel(0, 10000)
        page.wait_for_timeout(3000)

        current_count = page.locator(listing_sel).count()

        if current_count >= max_results:
            items = page.locator(listing_sel).all()[:max_results]
            print(f"[{label}] Total coletado: {len(items)}")
            return [item.locator("xpath=..") for item in items]

        if current_count == previously_counted:
            items = page.locator(listing_sel).all()
            print(f"[{label}] Fim da lista. Total coletado: {len(items)}")
            return [item.locator("xpath=..") for item in items]

        previously_counted = current_count
        print(f"[{label}] Carregando... {current_count} resultados", end="\r")


def _parse_coordinates(url: str) -> tuple[float, float]:
    """Extrai latitude e longitude da URL do Google Maps."""
    raw = url.split("/@")[-1].split("/")[0]
    lat, lon = raw.split(",")[:2]
    return float(lat), float(lon)


def _extract_business_from_page(page: Page, search_query: str) -> Business:
    """
    Lê os dados da empresa no painel lateral do Maps.

    Args:
        page: Instância ativa da página Playwright.
        search_query: Termo de busca original para categorização.

    Returns:
        Objeto Business preenchido.
    """

    def get_text(selector: str) -> str:
        loc = page.locator(selector)
        return loc.all()[0].inner_text() if loc.count() > 0 else ""

    business = Business()
    business.name = page.locator(SELECTORS["name"]).inner_text().strip()
    business.address = get_text(SELECTORS["address"])

    website_text = get_text(SELECTORS["website"])
    if website_text:
        business.domain = website_text
        business.website = f"https://www.{website_text}"

    business.phone_number = get_text(SELECTORS["phone"])

    reviews_raw = get_text(SELECTORS["reviews_count"])
    digits = "".join(filter(str.isdigit, reviews_raw))
    business.reviews_count = int(digits) if digits else 0

    avg_loc = page.locator(SELECTORS["reviews_avg"])
    if avg_loc.count() > 0:
        avg_text = (avg_loc.get_attribute("aria-label") or "0").split()[0]
        business.reviews_average = float(avg_text.replace(",", "."))
    else:
        business.reviews_average = 0.0

    parts = search_query.split(" in ")
    business.category = parts[0].strip()
    business.location = parts[-1].strip()
    business.latitude, business.longitude = _parse_coordinates(page.url)

    return business


def _enrich_business_contacts(business: Business, label: str) -> None:
    """Visita o site do lead e preenche `emails` e `scraped_phones`."""
    if not (business.website and business.website.startswith("http")):
        business.emails = ""
        business.scraped_phones = ""
        return

    print(f"  [{label}] Buscando contatos em {business.website}...", end=" ", flush=True)
    emails, phones = scrape_contact_info(business.website)
    business.emails = ", ".join(emails)
    business.scraped_phones = ", ".join(phones)

    email_log = f"Email: {', '.join(emails)}" if emails else "Email: Não achou"
    phone_log = f"Tel: {', '.join(phones)}" if phones else "Tel: Não achou"
    print(f"-> {email_log} | {phone_log}")


def scrape_query(index: int, search_query: str, max_results: int) -> None:
    """
    Executa o pipeline completo para uma única busca no Google Maps:
    coleta leads, enriquece contatos e salva CSV/XLSX.

    Projetado para rodar em processo independente via ProcessPoolExecutor.

    Args:
        index: Índice da busca para logging.
        search_query: Termo de busca (ex.: "Imobiliária em Curitiba - PR").
        max_results: Número máximo de resultados a coletar.
    """
    search_query = search_query.strip()
    collection = BusinessCollection()
    safe_name = search_query.replace(" ", "_")
    output_path = os.path.join(collection.output_dir, f"{safe_name}.xlsx")

    if os.path.exists(output_path):
        print(f"[{index}] PULANDO (já concluído): {search_query}")
        return

    print(f"[{index}] Iniciando: {search_query}")

    with sync_playwright() as playwright:
        headless = os.getenv("HEADLESS", "false").lower() == "true"
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page(locale="pt-BR")

        page.goto("https://www.google.com/maps", timeout=60_000)
        _accept_cookie_consent(page)

        search_box = page.locator(SELECTORS["search_box"])
        search_box.first.wait_for(state="visible", timeout=30_000)
        search_box.first.fill(search_query)
        page.wait_for_timeout(3000)
        page.keyboard.press("Enter")
        page.wait_for_timeout(5000)

        listings = []
        try:
            page.locator(SELECTORS["listing"]).first.wait_for(state="visible", timeout=10_000)
            page.hover(SELECTORS["listing"])
            listings = _scroll_until_loaded(page, max_results, search_query)
        except Exception:
            if page.locator(SELECTORS["name"]).count() > 0:
                print(f"[{index}] Resultado único direto detectado: {search_query}")
                try:
                    business = _extract_business_from_page(page, search_query)
                    _enrich_business_contacts(business, search_query)
                    collection.add(business)
                except Exception as exc:
                    print(f"  [{search_query}] Erro ao processar lead único: {exc}")
            else:
                print(f"[{index}] Nenhum resultado encontrado para: {search_query}")

        for listing in listings:
            try:
                listing.click()
                page.wait_for_timeout(2000)
                business = _extract_business_from_page(page, search_query)
                _enrich_business_contacts(business, search_query)
                collection.add(business)
            except Exception as exc:
                print(f"  [{search_query}] Erro ao processar lead: {exc}")

        browser.close()

    collection.save(safe_name)
    print(f"[{index}] Concluído: {search_query} — {len(collection)} leads salvos.")


# ---------------------------------------------------------------------------
# Entrypoint / CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
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


def _load_search_list(search_arg: Optional[str]) -> list[str]:
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

if __name__ == "__main__":
    main()
