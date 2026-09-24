import json
import os
import re

import requests
from bs4 import BeautifulSoup


PRODUCTS = [
    {
        "name": "Pokémon 30 Jahre Top-Trainer-Box",
        "url": "https://www.mediamarkt.at/de/product/_pokemon-company-international-top-trainer-box-30-jahre-sammelkarten-2087300.html",
    },
    {
        "name": "Pokémon 30 Jahre Ultra-Premium-Kollektion Tag",
        "url": "https://www.mediamarkt.at/de/product/_pokemon-company-international-30-jahre-ultra-premium-kollekt-tag-sammelkarten-2090549.html",
    },
    {
        "name": "Pokémon 30 Jahre Ultra-Premium-Kollektion Nacht",
        "url": "https://www.mediamarkt.at/de/product/_pokemon-company-international-30-jahre-ultra-premium-kollekt-nacht-sammelkarten-2090548.html",
    },
    {
        "name": "Pokémon Top-Trainer-Box Mega-Entwicklung – Delta-Herrschaft",
        "url": "https://www.mediamarkt.at/de/product/_pokemon-company-international-top-trainer-box-mega-entwicklung-delta-herrschaft-sammelkarten-2090551.html",
    },
]


STATE_FILE = "state.json"
POKEMON_CENTER_STATE_FILE = "pokemoncenter_state.json"

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.6 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "products": {},
            "telegram_update_offset": 0,
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        state.setdefault("products", {})
        state.setdefault("telegram_update_offset", 0)

        return state

    except Exception:
        return {
            "products": {},
            "telegram_update_offset": 0,
        }


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_pokemon_center_state():
    if not os.path.exists(POKEMON_CENTER_STATE_FILE):
        return {
            "product_urls": [],
            "page_hash": "",
            "queue_detected": False,
        }

    try:
        with open(POKEMON_CENTER_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return {
            "product_urls": [],
            "page_hash": "",
            "queue_detected": False,
        }


def telegram_send(message, chat_id=None):
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    response.raise_for_status()


def normalize(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def check_product(product):
    try:
        response = requests.get(
            product["url"],
            headers=HEADERS,
            timeout=30,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        page_text = normalize(
            soup.get_text(" ", strip=True)
        )

        buttons = []

        for element in soup.find_all(["button", "a"]):
            text = element.get_text(" ", strip=True)

            if text:
                buttons.append(normalize(text))

        combined = page_text + " " + " ".join(buttons)

        unavailable_terms = [
            "leider keine lieferung möglich",
            "benachrichtige mich",
            "vorbestellung ist bald möglich",
            "derzeit nicht verfügbar",
            "nicht verfügbar",
            "ausverkauft",
        ]

        available_terms = [
            "in den warenkorb",
            "vorbestellen",
            "jetzt kaufen",
            "kaufen",
        ]

        unavailable = any(
            term in combined
            for term in unavailable_terms
        )

        available = any(
            term in combined
            for term in available_terms
        )

        if unavailable:
            available = False

        return {
            "available": available,
            "error": False,
        }

    except Exception as e:
        print(f"Fehler bei {product['name']}: {e}")

        return {
            "available": False,
            "error": True,
        }


def create_status_message(state):
    products = state.get("products", {})

    lines = [
        "🔎 AKTUELLER STATUS",
        "",
        "🛒 MEDIAMARKT",
    ]

    for product in PRODUCTS:
        old_status = products.get(
            product["url"],
            {},
        )

        if old_status.get("available", False):
            status = "🟢 VERFÜGBAR"

        elif old_status.get("error", False):
            status = "⚠️ FEHLER BEIM LETZTEN CHECK"

        else:
            status = "🔴 NICHT VERFÜGBAR"

        lines.append(
            f"{status} – {product['name']}"
        )

    pokemon_state = load_pokemon_center_state()

    pokemon_products = pokemon_state.get(
        "product_urls",
        [],
    )

    queue_detected = pokemon_state.get(
        "queue_detected",
        False,
    )

    page_hash = pokemon_state.get(
        "page_hash",
        "",
    )

    lines.extend(
        [
            "",
            "🟣 POKÉMON CENTER",
            "",
            f"🆕 Erkannte Produkt-Links: "
            f"{len(pokemon_products)}",
        ]
    )

    if queue_detected:
        lines.append(
            "🚨 WARTESCHLANGE: ERKANNT"
        )
    else:
        lines.append(
            "🟢 WARTESCHLANGE: NICHT ERKANNT"
        )

    if page_hash:
        lines.append(
            "🔔 Seitenstatus: Überwachung aktiv"
        )
    else:
        lines.append(
            "⚠️ Seitenstatus: Noch kein Status"
        )

    lines.extend(
        [
            "",
            "ℹ️ Status basiert auf dem "
            "letzten erfolgreichen Monitor-Lauf.",
        ]
    )

    return "\n".join(lines)


def process_telegram_commands(state):
    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/getUpdates"
    )

    offset = int(
        state.get(
            "telegram_update_offset",
            0,
        )
    )

    print(
        f"Telegram: Suche nach neuen Nachrichten "
        f"ab offset {offset}"
    )

    try:
        response = requests.get(
            url,
            params={
                "offset": offset,
                "limit": 20,
                "timeout": 2,
            },
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

    except Exception as e:
        print(
            f"Telegram getUpdates Fehler: {e}"
        )
        return

    if not data.get("ok"):
        print(
            f"Telegram API Fehler: {data}"
        )
        return

    updates = data.get("result", [])

    print(
        f"Telegram: {len(updates)} neue Nachricht(en)"
    )

    for update in updates:

        update_id = update.get("update_id")

        if update_id is None:
            continue

        state["telegram_update_offset"] = (
            update_id + 1
        )

        message = update.get("message", {})

        chat = message.get("chat", {})

        chat_id = str(
            chat.get("id", "")
        )

        text = message.get("text", "")

        print(
            f"Telegram Nachricht: "
            f"chat_id={chat_id}, text={text!r}"
        )

        if chat_id != TELEGRAM_CHAT_ID:
            print(
                "Telegram Nachricht ignoriert: "
                "falsche Chat-ID."
            )
            continue

        command = text.strip().lower()

        if command == "/update":

            print(
                "✅ /update erkannt – sende Status."
            )

            try:
                telegram_send(
                    create_status_message(state),
                    chat_id,
                )

                print(
                    "✅ /update beantwortet."
                )

            except Exception as e:
                print(
                    f"Fehler beim Senden von /update: {e}"
                )


def check_mediamarkt(state):

    products_state = state.get(
        "products",
        {},
    )

    for product in PRODUCTS:

        print(
            f"Prüfe: {product['name']}"
        )

        result = check_product(product)

        current_available = result["available"]
        current_error = result["error"]

        previous = products_state.get(
            product["url"],
            {},
        )

        previous_available = previous.get(
            "available",
            False,
        )

        if (
            current_available
            and not previous_available
        ):

            message = (
                "🚨 POKÉMON PRODUKT VERFÜGBAR!\n\n"
                f"{product['name']}\n\n"
                f"👉 {product['url']}"
            )

            try:
                telegram_send(message)

                print(
                    "Telegram-Benachrichtigung gesendet."
                )

            except Exception as e:
                print(
                    f"Telegram Fehler: {e}"
                )

        products_state[
            product["url"]
        ] = {
            "available": current_available,
            "error": current_error,
        }

    state["products"] = products_state


def check():

    state = load_state()

    print(
        "=== MediaMarkt Pokémon Monitor ==="
    )

    # 1. MediaMarkt prüfen
    check_mediamarkt(state)

    # 2. State speichern
    save_state(state)

    print(
        "MediaMarkt Check erfolgreich."
    )

    # 3. Telegram NACH dem Check prüfen
    process_telegram_commands(state)

    # 4. State erneut speichern,
    # damit der Telegram-Offset erhalten bleibt.
    save_state(state)

    print(
        "=== Monitor beendet ==="
    )


if __name__ == "__main__":
    check()
