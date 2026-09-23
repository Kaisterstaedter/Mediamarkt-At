import os
import json
import hashlib
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


POKEMON_CENTER_URL = "https://www.pokemoncenter.com/en-de"

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "pokemoncenter_state.json"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.6 Mobile/15E148 Safari/604.1"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
}


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


def normalize_text(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def detect_queue(html, text):
    combined = normalize_text(html + " " + text)

    queue_terms = [
        "virtual queue",
        "virtual queue is currently",
        "waiting room",
        "waiting room is currently",
        "please wait",
        "you are in line",
        "you're in line",
        "queue-it",
        "queueit",
        "wait your turn",
        "waiting to enter",
        "warteschlange",
        "wartebereich",
        "bitte warten",
    ]

    return any(term in combined for term in queue_terms)


def extract_product_links(soup):
    urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()

        if not href:
            continue

        absolute = urljoin(POKEMON_CENTER_URL, href)

        if "pokemoncenter.com" not in absolute:
            continue

        # Product-Seiten von Pokémon Center erkennen
        if "/product/" in absolute.lower():
            clean = absolute.split("?")[0].split("#")[0]
            urls.add(clean)

    return sorted(urls)


def create_page_hash(soup):
    # Nicht jede Kleinigkeit wie Session-IDs oder Zeitstempel
    # soll eine Änderung auslösen.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)

    # Normalisieren
    text = re.sub(r"\s+", " ", text).strip()

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check():
    state = load_state()

    response = requests.get(
        POKEMON_CENTER_URL,
        headers=HEADERS,
        timeout=30,
        allow_redirects=True,
    )

    response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # ---------------------------------------------------------
    # 1. WARTESCHLANGE
    # ---------------------------------------------------------

    queue_detected = detect_queue(html, text)

    if queue_detected and not state.get("queue_detected", False):

        telegram(
            "🚨 POKÉMON CENTER WARTESCHLANGE ERKANNT!\n\n"
            "Eine Virtual Queue / Warteschlange wurde auf "
            "Pokémon Center erkannt.\n\n"
            "👉 Jetzt sofort öffnen:\n"
            f"{POKEMON_CENTER_URL}\n\n"
            "⚠️ Wenn du bereits in der Queue bist, "
            "die Seite nicht aktualisieren."
        )

    state["queue_detected"] = queue_detected

    # ---------------------------------------------------------
    # 2. PRODUKTE
    # ---------------------------------------------------------

    current_products = extract_product_links(soup)
    previous_products = set(state.get("product_urls", []))

    new_products = [
        url for url in current_products
        if url not in previous_products
    ]

    if new_products:

        message = (
            "🆕 NEUE PRODUKTE BEI POKÉMON CENTER!\n\n"
        )

        for url in new_products[:20]:
            message += f"👉 {url}\n"

        telegram(message)

    # ---------------------------------------------------------
    # 3. SEITENÄNDERUNG
    # ---------------------------------------------------------

    current_hash = create_page_hash(
        BeautifulSoup(html, "html.parser")
    )

    previous_hash = state.get("page_hash", "")

    # Beim ersten Lauf keine Änderungs-Meldung schicken.
    if previous_hash and current_hash != previous_hash:

        telegram(
            "🔔 POKÉMON CENTER SEITENÄNDERUNG ERKANNT!\n\n"
            "Die überwachte Seite hat sich seit dem letzten "
            "Check verändert.\n\n"
            f"👉 {POKEMON_CENTER_URL}"
        )

    # ---------------------------------------------------------
    # STATE SPEICHERN
    # ---------------------------------------------------------

    state["product_urls"] = current_products
    state["page_hash"] = current_hash

    save_state(state)

    print(
        f"Pokémon Center geprüft | "
        f"Produkte: {len(current_products)} | "
        f"Queue: {queue_detected} | "
        f"Neue Produkte: {len(new_products)}"
    )


if __name__ == "__main__":
    check()
