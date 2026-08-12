"""Enriquecimento de contatos: extrai e-mails/telefones de sites via HTTP + regex."""

from __future__ import annotations

import concurrent.futures
import csv
import glob
import os
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from atlasleads.constants import (
    CONTACT_KEYWORDS,
    DATA_DIR,
    EMAIL_REGEX,
    HTTP_HEADERS,
    HTTP_TIMEOUT,
    MAX_CONTACT_PAGES,
    PHONE_REGEX,
)


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
