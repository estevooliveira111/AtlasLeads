import datetime
from playwright.sync_api import sync_playwright
from dataclasses import dataclass, asdict, field
import pandas as pd
import argparse
import os
import sys
import concurrent.futures
from emails import scrape_site

@dataclass
class Business:
    """holds business data"""
    name: str = None
    address: str = None
    domain: str = None
    website: str = None
    phone_number: str = None
    category: str = None
    location: str = None
    reviews_count: int = None
    reviews_average: float = None
    latitude: float = None
    longitude: float = None
    emails: str = None
    scraped_phones: str = None
    
    def __hash__(self):
        """Make Business hashable for duplicate detection."""
        hash_fields = [self.name]
        if self.domain:
            hash_fields.append(f"domain:{self.domain}")
        if self.website:
            hash_fields.append(f"website:{self.website}")
        if self.phone_number:
            hash_fields.append(f"phone:{self.phone_number}")
        
        return hash(tuple(hash_fields))

@dataclass
class BusinessList:
    """holds list of Business objects,
    and save to both excel and csv
    """
    business_list: list[Business] = field(default_factory=list)
    _seen_businesses: set = field(default_factory=set, init=False)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    save_at = os.path.join('GMaps Data', today)
    os.makedirs(save_at, exist_ok=True)

    def add_business(self, business: Business):
        """Add a business to the list if it's not a duplicate based on key attributes"""
        business_hash = hash(business)
        if business_hash not in self._seen_businesses:
            self.business_list.append(business)
            self._seen_businesses.add(business_hash)
    
    def dataframe(self):
        """transform business_list to pandas dataframe"""
        return pd.json_normalize(
            (asdict(business) for business in self.business_list), sep="_"
        )

    def save_to_excel(self, filename):
        """saves pandas dataframe to excel (xlsx) file"""
        self.dataframe().to_excel(f"{self.save_at}/{filename}.xlsx", index=False)

    def save_to_csv(self, filename):
        """saves pandas dataframe to csv file"""
        self.dataframe().to_csv(f"{self.save_at}/{filename}.csv", index=False)

def extract_coordinates_from_url(url: str) -> tuple[float, float]:
    """helper function to extract coordinates from url"""
    coordinates = url.split('/@')[-1].split('/')[0]
    return float(coordinates.split(',')[0]), float(coordinates.split(',')[1])

def process_search_query(search_for_index, search_for, total):
    """Processes a single search query in its own Playwright instance"""
    search_for = search_for.strip()
    # Check if this search has already been completed today
    filename_clean = search_for.replace(' ', '_')
    file_path_check = os.path.join(BusinessList.save_at, f"{filename_clean}.xlsx")
    
    if os.path.exists(file_path_check):
        print(f"-----\n{search_for_index} - {search_for} (PULANDO: Já concluído)")
        return

    print(f"-----\n{search_for_index} - {search_for}".strip())

    with sync_playwright() as p:
        headless_mode = os.getenv('HEADLESS', 'false').lower() == 'true'
        browser = p.chromium.launch(headless=headless_mode)
        page = browser.new_page(locale="pt-BR")

        page.goto("https://www.google.com/maps", timeout=60000)
        
        # Handle cookie consent if it appears
        try:
            consent_button = page.locator('button[aria-label="Accept all"], button[aria-label="Agree"], button[aria-label="Aceitar tudo"], button[aria-label="Concordo"], button:has-text("Accept all"), button:has-text("Agree"), button:has-text("Aceitar tudo"), button:has-text("Concordo")')
            if consent_button.count() > 0:
                consent_button.first.click()
                page.wait_for_timeout(2000)
        except:
            pass

        # Use a more robust selector for the search box
        search_box = page.locator('input#searchboxinput, input[name="q"], input[role="combobox"]')
        search_box.first.wait_for(state="visible", timeout=30000)
        search_box.first.fill(search_for)
        page.wait_for_timeout(3000)

        page.keyboard.press("Enter")
        page.wait_for_timeout(5000)

        # scrolling
        page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')

        previously_counted = 0
        while True:
            page.mouse.wheel(0, 10000)
            page.wait_for_timeout(3000)

            if (page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').count() >= total):
                listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()[:total]
                listings = [listing.locator("xpath=..") for listing in listings]
                print(f"[{search_for}] Total Scraped: {len(listings)}")
                break
            else:
                if (page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').count() == previously_counted):
                    listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()
                    print(f"[{search_for}] Arrived at all available\nTotal Scraped: {len(listings)}")
                    break
                else:
                    previously_counted = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').count()
                    print(f"[{search_for}] Currently Scraped: {previously_counted}")

        business_list = BusinessList()

        # scraping
        for listing in listings:
            try:                        
                listing.click()
                page.wait_for_timeout(2000)

                name_attribute = 'h1.DUwDvf'
                address_xpath = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
                website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
                phone_number_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'
                review_count_xpath = '//div[@jsaction="pane.reviewChart.moreReviews"]//span'
                reviews_average_xpath = '//div[@jsaction="pane.reviewChart.moreReviews"]//div[@role="img"]'
                                                       
                business = Business()
               
                if name_value := page.locator(name_attribute).inner_text():
                    business.name = name_value.strip()
                else:
                    business.name = ""

                if page.locator(address_xpath).count() > 0:
                    business.address = page.locator(address_xpath).all()[0].inner_text()
                else:
                    business.address = ""

                if page.locator(website_xpath).count() > 0:
                    business.domain = page.locator(website_xpath).all()[0].inner_text()
                    business.website = f"https://www.{page.locator(website_xpath).all()[0].inner_text()}"
                else:
                    business.website = ""

                if page.locator(phone_number_xpath).count() > 0:
                    business.phone_number = page.locator(phone_number_xpath).all()[0].inner_text()
                else:
                    business.phone_number = ""
                    
                if page.locator(review_count_xpath).count() > 0:
                    reviews_count_text = page.locator(review_count_xpath).inner_text()
                    reviews_count_clean = "".join(filter(str.isdigit, reviews_count_text))
                    business.reviews_count = int(reviews_count_clean) if reviews_count_clean else 0
                else:
                    business.reviews_count = 0
                    
                if page.locator(reviews_average_xpath).count() > 0:
                    reviews_average_text = page.locator(reviews_average_xpath).get_attribute('aria-label').split()[0]
                    business.reviews_average = float(reviews_average_text.replace(',', '.'))
                else:
                    business.reviews_average = 0.0
            
                business.category = search_for.split(' in ')[0].strip()
                business.location = search_for.split(' in ')[-1].strip()
                business.latitude, business.longitude = extract_coordinates_from_url(page.url)

                if business.website and business.website.startswith("http"):
                    print(f"[{search_for}] Buscando contatos em: {business.website}...", end=" ", flush=True)
                    emails_set, phones_set = scrape_site(business.website)
                    business.emails = ", ".join(emails_set)
                    business.scraped_phones = ", ".join(phones_set)
                    print("Feito!")
                else:
                    business.emails = ""
                    business.scraped_phones = ""

                business_list.add_business(business)
            except Exception as e:
                print(f'[{search_for}] Error occurred: {e}')
        
        # output
        business_list.save_to_excel(f"{search_for}".replace(' ', '_'))
        business_list.save_to_csv(f"{search_for}".replace(' ', '_'))

        browser.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--search", type=str)
    parser.add_argument("-t", "--total", type=int)
    parser.add_argument("-w", "--workers", type=int, default=1, help="Número de processos paralelos (clusters)")
    args = parser.parse_args()
    
    if args.search:
        search_list = [args.search]
        
    if args.total:
        total = args.total
    else:
        total = 1_000_000

    if not args.search:
        search_list = []
        input_file_name = 'input.txt'
        input_file_path = os.path.join(os.getcwd(), input_file_name)
        if os.path.exists(input_file_path):
            with open(input_file_path, 'r') as file:
                search_list = file.readlines()
                
        if len(search_list) == 0:
            print('Error occured: You must either pass the -s search argument, or add searches to input.txt')
            sys.exit()

    workers = args.workers
    print(f"Iniciando raspagem com {workers} worker(s) paralelos...")

    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = []
        for index, search in enumerate(search_list):
            futures.append(executor.submit(process_search_query, index, search, total))
        
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Worker process falhou: {e}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f'Failed err: {e}')
