import json, os, re, time
import requests
from pathlib import Path
import requests
from bs4 import BeautifulSoup

PRODUCTS = [
    ("Pokémon Top-Trainer-Box 30 Jahre", "https://www.mediamarkt.at/de/product/_pokemon-company-international-top-trainer-box-30-jahre-sammelkarten-2087300.html"),
    ("Pokémon 30 Jahre Ultra-Premium-Kollektion Tag", "https://www.mediamarkt.at/de/product/_pokemon-company-international-30-jahre-ultra-premium-kollekt-tag-sammelkarten-2090549.html"),
    ("Pokémon 30 Jahre Ultra-Premium-Kollektion Nacht", "https://www.mediamarkt.at/de/product/_pokemon-company-international-30-jahre-ultra-premium-kollekt-nacht-sammelkarten-2090548.html"),
    ("Pokémon Top-Trainer-Box Mega-Entwicklung – Delta-Herrschaft", "https://www.mediamarkt.at/de/product/_pokemon-company-international-top-trainer-box-mega-entwicklung-delta-herrschaft-sammelkarten-2090551.html"),
]

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = Path("state.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1", "Accept-Language": "de-AT,de;q=0.9,en;q=0.8"}

def norm(s): return re.sub(r"\s+", " ", s or "").strip().lower()

def load():
    try: return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception: return {}

def save(s): STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")

def telegram(msg):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "disable_web_page_preview": False}, timeout=20)
    r.raise_for_status()

def check(name, url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = norm(soup.get_text(" ", strip=True))
    actions = norm(" ".join(x.get_text(" ", strip=True) for x in soup.select("button,a,[role='button']")))
    if "in den warenkorb" in actions or "vorbestellen" in actions:
        status = "available"
    elif any(x in text for x in ("leider keine lieferung möglich", "benachrichtige mich", "vorbestellung ist bald möglich")):
        status = "unavailable"
    else:
        status = "unknown"
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else name
    return {"status": status, "title": title, "url": url, "checked_at": int(time.time())}

def main():
    state = load()
    for name, url in PRODUCTS:
        try:
            result = check(name, url)
            previous = state.get(url, {}).get("status")
            print(name, "->", result["status"])
            state[url] = result
            if result["status"] == "available" and previous != "available":
                telegram(f"🚨 MEDIA MARKT VERFÜGBAR!\n\n{result['title']}\n\nJetzt manuell bestellen/vorbestellen:\n{url}")
        except Exception as e:
            print("FEHLER:", name, e)
    save(state)

if __name__ == "__main__": main()
