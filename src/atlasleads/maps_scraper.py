"""Scraper do Google Maps via Playwright: coleta listagens e delega o enriquecimento de contatos."""

from __future__ import annotations

import os

from playwright.sync_api import Page, sync_playwright

from atlasleads.constants import SELECTORS
from atlasleads.enrichment import scrape_contact_info
from atlasleads.models import Business, BusinessCollection


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

    parts = search_query.split(" em ")
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
