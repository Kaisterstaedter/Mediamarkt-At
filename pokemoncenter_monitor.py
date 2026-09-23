import os
import json
import hashlib
import re
from urllib.parse import urljoin

import requests
from playwright.sync_api import sync_playwright


POKEMON_CENTER_URL = "https://www.pokemoncenter.com/en-de"
STATE_FILE = "pokemoncenter_state.json"

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "product_urls": [],
            "page_hash": "",
            "queue_detected": False,
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "product_urls": [],
            "page_hash": "",
            "queue_detected": False,
        }


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def telegram(message):
    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    response.raise_for_status()


def normalize(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def detect_queue(page):
    current_url = page.url.lower()

    try:
        title = page.title()
    except Exception:
        title = ""

    try:
        body = page.locator("body").inner_text(timeout=10000)
    except Exception:
        body = ""

    combined = normalize(
        current_url + " " + title + " " + body
    )

    queue_terms = [
        "virtual queue",
        "waiting room",
        "you are in line",
        "you're in line",
        "please wait",
        "wait your turn",
        "waiting to enter",
        "queue-it",
        "queueit",
        "warteschlange",
        "wartebereich",
        "bitte warten",
    ]

    return any(term in combined for term in queue_terms)


def extract_product_links(page):
    urls = set()

    links = page.locator("a[href]").all()

    for link in links:
        try:
            href = link.get_attribute("href")
        except Exception:
            continue

        if not href:
            continue

        absolute = urljoin(
            POKEMON_CENTER_URL,
            href
        )

        if "pokemoncenter.com" not in absolute:
            continue

        if "/product/" in absolute.lower():

            clean = (
                absolute
                .split("?")[0]
                .split("#")[0]
            )

            urls.add(clean)

    return sorted(urls)


def page_hash(page):
    try:
        text = page.locator("body").inner_text(
            timeout=10000
        )
    except Exception:
        text = ""

    text = normalize(text)

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def check():

    state = load_state()

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            viewport={
                "width": 390,
                "height": 844
            },
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/18.6 Mobile/15E148 Safari/604.1"
            ),
            locale="de-DE",
            timezone_id="Europe/Berlin",
        )

        page = context.new_page()

        try:

            print(
                "Öffne Pokémon Center..."
            )

            response = page.goto(
                POKEMON_CENTER_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            print(
                f"Start-URL: {POKEMON_CENTER_URL}"
            )

            print(
                f"Aktuelle URL: {page.url}"
            )

            if response:
                print(
                    f"HTTP Status: {response.status}"
                )

            # Zeit geben, damit JavaScript,
            # Weiterleitungen und Queue-Systeme
            # vollständig reagieren können.
            page.wait_for_timeout(10000)

            print(
                f"URL nach JavaScript: {page.url}"
            )

            # -------------------------------------------------
            # WARTESCHLANGE
            # -------------------------------------------------

            queue_detected = detect_queue(page)

            previous_queue = state.get(
                "queue_detected",
                False
            )

            print(
                f"Queue erkannt: {queue_detected}"
            )

            if queue_detected and not previous_queue:

                telegram(
                    "🚨 POKÉMON CENTER WARTESCHLANGE "
                    "ERKANNT!\n\n"
                    "Eine Virtual Queue / Warteschlange "
                    "wurde erkannt.\n\n"
                    "👉 Jetzt öffnen:\n"
                    f"{POKEMON_CENTER_URL}\n\n"
                    "⚠️ Wenn du bereits in der Queue bist, "
                    "die Seite nicht aktualisieren."
                )

            state["queue_detected"] = queue_detected

            # -------------------------------------------------
            # PRODUKTE
            # -------------------------------------------------

            current_products = extract_product_links(page)

            previous_products = set(
                state.get(
                    "product_urls",
                    []
                )
            )

            new_products = [
                url
                for url in current_products
                if url not in previous_products
            ]

            print(
                f"Produkt-Links gefunden: "
                f"{len(current_products)}"
            )

            print(
                f"Neue Produkte: "
                f"{len(new_products)}"
            )

            if new_products:

                message = (
                    "🆕 NEUE PRODUKTE BEI "
                    "POKÉMON CENTER!\n\n"
                )

                for url in new_products[:20]:
                    message += (
                        f"👉 {url}\n"
                    )

                telegram(message)

            # -------------------------------------------------
            # SEITENÄNDERUNG
            # -------------------------------------------------

            current_hash = page_hash(page)

            previous_hash = state.get(
                "page_hash",
                ""
            )

            if (
                previous_hash
                and current_hash != previous_hash
            ):

                telegram(
                    "🔔 POKÉMON CENTER "
                    "SEITENÄNDERUNG ERKANNT!\n\n"
                    "Die überwachte Seite hat sich "
                    "seit dem letzten Check verändert.\n\n"
                    f"👉 {POKEMON_CENTER_URL}"
                )

            state["product_urls"] = current_products
            state["page_hash"] = current_hash

            save_state(state)

            print(
                "Pokémon Center Check erfolgreich."
            )

        finally:

            browser.close()


if __name__ == "__main__":
    check()
