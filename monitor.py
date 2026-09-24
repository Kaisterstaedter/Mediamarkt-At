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

        if "products" not in state:
            state["products"] = {}

        if "telegram_update_offset" not in state:
            state["telegram_update_offset"] = 0

        return state

    except Exception:
        return {
            "products": {},
            "telegram_update_offset": 0,
        }


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )


def telegram_send(message):
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

        for element in soup.find_all(
            ["button", "a"]
        ):
            text = element.get_text(
                " ",
                strip=True,
            )

            if text:
                buttons.append(
                    normalize(text)
                )

        button_text = " ".join(buttons)

        combined = (
            page_text
            + " "
            + button_text
        )

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
        print(
            f"Fehler bei {product['name']}: {e}"
        )

        return {
            "available": False,
            "error": True,
        }


def process_telegram_commands(state):
    """
    Prüft Telegram auf /update.
    Bereits verarbeitete Nachrichten werden über
    telegram_update_offset nicht erneut verarbeitet.
    """

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

    try:
        response = requests.get(
            url,
            params={
                "offset": offset,
                "limit": 20,
                "timeout": 1,
            },
            timeout=10,
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
            "Telegram getUpdates war nicht erfolgreich."
        )
        return

    updates = data.get(
        "result",
        [],
    )

    for update in updates:

        update_id = update.get(
            "update_id"
        )

        if update_id is None:
            continue

        state["telegram_update_offset"] = (
            update_id + 1
        )

        message = update.get(
            "message",
            {},
        )

        chat = message.get(
            "chat",
            {},
        )

        chat_id = str(
            chat.get(
                "id",
                "",
            )
        )

        text = message.get(
            "text",
            "",
        )

        if chat_id != TELEGRAM_CHAT_ID:
            continue

        command = text.strip().lower()

        if command == "/update":

            lines = [
                "🔎 AKTUELLER STATUS",
                "",
                "MediaMarkt:",
            ]

            products = state.get(
                "products",
                {},
            )

            for product in PRODUCTS:

                old_status = products.get(
                    product["url"],
                    {},
                )

                if old_status.get(
                    "available",
                    False,
                ):
                    status = "🟢 VERFÜGBAR"
                elif old_status.get(
                    "error",
                    False,
                ):
                    status = "⚠️ Fehler beim letzten Check"
                else:
                    status = "🔴 NICHT VERFÜGBAR"

                lines.append(
                    f"{status} – {product['name']}"
                )

            lines.extend(
                [
                    "",
                    "ℹ️ Der Status basiert auf dem "
                    "letzten erfolgreichen Monitor-Lauf.",
                ]
            )

            try:
                telegram_send(
                    "\n".join(lines)
                )

                print(
                    "/update beantwortet."
                )

            except Exception as e:
                print(
                    f"Fehler beim Senden von /update: {e}"
                )


def check():

    state = load_state()

    # Telegram-Befehle zuerst prüfen.
    process_telegram_commands(
        state
    )

    products_state = state.get(
        "products",
        {},
    )

    for product in PRODUCTS:

        print(
            f"Prüfe: {product['name']}"
        )

        result = check_product(
            product
        )

        current_available = result[
            "available"
        ]

        current_error = result[
            "error"
        ]

        previous = products_state.get(
            product["url"],
            {},
        )

        previous_available = previous.get(
            "available",
            False,
        )

        # Nur bei Wechsel auf verfügbar
        # Telegram benachrichtigen.
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
                telegram_send(
                    message
                )

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

    save_state(state)

    print(
        "MediaMarkt Check erfolgreich."
    )


if __name__ == "__main__":
    check()
