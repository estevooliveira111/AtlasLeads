import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import csv
import glob
import os
import concurrent.futures

EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
PHONE_REGEX = r"(?:\+?55\s?)?\(?\b[1-9]{2}\)?\s?(?:9\s?\d{4}|\d{4})[-.\s]?\d{4}\b"

def extract_emails(text):
    return set(re.findall(EMAIL_REGEX, text))

def extract_phones(text):
    return set(re.findall(PHONE_REGEX, text))

def fetch(url):
    try:
        r = requests.get(url, timeout=10, 
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })
        return r.text if r.status_code == 200 else ""
    except:
        return ""

def fetch_and_extract(url):
    html = fetch(url)
    return extract_emails(html), extract_phones(html)

def scrape_site(base_url):
    emails = set()
    phones = set()

    html = fetch(base_url)
    if not html:
        return emails, phones

    soup = BeautifulSoup(html, "html.parser")
    emails |= extract_emails(html)
    phones |= extract_phones(html)

    # procurar páginas comuns de contato
    links = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").lower()
        if any(keyword in href for keyword in ["contact", "contato", "about", "phone", "suporte", "support"]):
            links.append(urljoin(base_url, href))

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_and_extract, link) for link in links[:5]]
        for future in concurrent.futures.as_completed(futures):
            try:
                em, ph = future.result()
                emails |= em
                phones |= ph
            except Exception:
                pass

    return emails, phones

def process_csv_files():
    base_dir = "GMaps Data"
    # Find all csv files inside the GMaps Data directory
    csv_files = glob.glob(os.path.join(base_dir, "**/*.csv"), recursive=True)
    
    for file_path in csv_files:
        print(f"Processing file: {file_path}")
        
        # Read the CSV content
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            if not fieldnames:
                continue
            
            fieldnames = list(fieldnames)
            if "emails" not in fieldnames:
                fieldnames.append("emails")
            if "scraped_phones" not in fieldnames:
                fieldnames.append("scraped_phones")
                
            rows = list(reader)
            
        # Process each row
        modified = False
        for row in rows:
            website = row.get("website", "")
            
            needs_scraping = False
            if website and website.startswith("http"):
                if "emails" not in row or "scraped_phones" not in row:
                    needs_scraping = True
            
            # Scrape if there's a valid website and emails or phones haven't been fetched yet
            if needs_scraping:
                print(f"  Scraping {website}...", end=" ", flush=True)
                emails, phones = scrape_site(website)
                
                res_email = f"Email: {', '.join(emails)}" if emails else "Email: Não achou"
                res_phone = f"Telefone: {', '.join(phones)}" if phones else "Telefone: Não achou"
                print(f"-> {res_email} | {res_phone}")
                
                row["emails"] = ", ".join(emails)
                row["scraped_phones"] = ", ".join(phones)
                modified = True
            else:
                if "emails" not in row:
                    row["emails"] = ""
                if "scraped_phones" not in row:
                    row["scraped_phones"] = ""
                
        # Write back to the CSV
        with open(file_path, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            
if __name__ == "__main__":
    process_csv_files()
