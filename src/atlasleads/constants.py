"""Constantes compartilhadas: caminhos, limites, regexes e seletores do Maps."""

from __future__ import annotations

import re

DATA_DIR: str = "output"
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
    "phone": (
        '//button[contains(@data-item-id,"phone:tel:")]'
        '//div[contains(@class,"fontBodyMedium")]'
    ),
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
