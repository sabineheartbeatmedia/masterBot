import os
import logging
import html
import xml.etree.ElementTree as ET
from urllib.parse import quote
import time

import httpx
import anthropic

# ── Config ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ANTHROPIC_MODEL   = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# Apify ist optional – nur wenn Token gesetzt ist, wird Instagram durchsucht
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")

# Trend-Suchbegriffe (Google) – breit genug für Treffer
NEWS_KEYWORDS = [
    "Instagram Trends",
    "Social Media Trends DACH",
    "Personal Branding Positionierung",
    "LinkedIn Content Trends",
    "Instagram neue Funktion Update",
    "KI Marketing Selbstständige",
    "Sichtbarkeit Selbstständige",
]

# Instagram Hashtags (nur wenn APIFY_TOKEN gesetzt) – wir holen die TOP-Beiträge
INSTAGRAM_HASHTAGS = [
    "socialmediamarketing",
    "personalbranding",
    "sichtbarwerden",
    "selbstständigkeit",
    "contentplanung",
    "instagramtipps",
    "authentischsichtbar",
    "sichzeigen",
]

APIFY_BASE = "https://api.apify.com/v2"
# ─────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)


# ── Google News (kostenlos, ohne Key) ───────────────────────────────────────

def fetch_news(keyword: str, limit: int = 4) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        + quote(keyword)
        + "&hl=de&gl=AT&ceid=AT:de"
    )
    items = []
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:limit]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            source_el = item.find("{*}source")
            source = source_el.text if source_el is not None else ""
            items.append({"title": html.unescape(title), "link": link, "source": source})
    except Exception as e:
        log.error("News-Fehler bei '%s': %s", keyword, e)
    return items


# ── Instagram via Apify (optional) ───────────────────────────────────────────

def fetch_instagram(hashtags: list[str], limit: int = 10) -> list[dict]:
    if not APIFY_TOKEN:
        return []
    headers = {"Authorization": f"Bearer {APIFY_TOKEN}"}
    payload = {"hashtags": hashtags, "resultsLimit": limit, "resultsType": "top"}
    posts = []
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(
                f"{APIFY_BASE}/acts/apify~instagram-hashtag-scraper/runs",
                headers=headers, json=payload,
            )
            r.raise_for_status()
            run_id = r.json()["data"]["id"]
            for _ in range(36):
                time.sleep(5)
                status = client.get(
                    f"{APIFY_BASE}/actor-runs/{run_id}", headers=headers
                ).json()["data"]["status"]
                if status == "SUCCEEDED":
                    break
                if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    return []
            data = client.get(
                f"{APIFY_BASE}/actor-runs/{run_id}/dataset/items", headers=headers
            ).json()
        for p in data:
            cap = (p.get("caption") or "").strip().replace("\n", " ")
            if cap:
                posts.append({"caption": cap[:200], "likes": p.get("likesCount", 0)})
    except Exception as e:
        log.error("Instagram/Apify-Fehler: %s", e)
    return posts


# ── Zusammenfassung mit Claude (in Sabines Stimme) ────────────────────────────

SYSTEM_PROMPT = """Du bist die Stimme von Sabine Weigl / Heartbeat Media.
Du erstellst ihren Trend-Radar 2x/Woche: Aus aktuellem Material (Google + Instagram Top-Beiträge)
filterst du heraus, was SIE für ihren Content aufgreifen kann.

STIMME: entschieden, ruhig, analytisch, klar im Standpunkt. Kurze, klare Sätze.
Signature: "Substanz schlägt Show." Relevanz statt Reichweite. System statt Tricks.
SATZMUSTER: "Das Problem ist nicht X, sondern Y." · "Viele glauben …, aber …" · "Nicht X. Sondern Y."

VERBOTENE WÖRTER: Klarheit, Leichtigkeit, next level, authentisch (im Trend-Sinn), Community Vibes,
Energie (esoterisch), Seelenbusiness, Mindset-Magic, Fülle, Manifestieren, weich, sanft, Herzensbusiness,
Impuls, Fühl mal rein. KEINE Gedankenstriche. Keine KI-Floskeln. Keine glattgebügelten Marketing-Sätze.

SABINES BRILLE — priorisiere Themen aus DIESEN Bereichen:
- Positionierung & Zielgruppe ausarbeiten (NICHT schnelles Wachstum)
- Authentische Sichtbarkeit, sich zeigen ohne Druck, sichtbar werden trotz Angst
- Struggles von Selbstständigen, die auf Instagram STARTEN
- Instagram-App verstehen: wo finde ich was, wie funktioniert welche Funktion
- KI für Zielgruppen- und Branding-Arbeit (NICHT für Hooks/Viral-Tricks)
- LinkedIn für Selbstständige (gib konkrete LinkedIn-Winkel)
- DACH / Österreich, nachhaltiger Content, wenig Zeit, ohne Marktschreien

TABU-THEMEN (ignorieren, auch wenn im Material): schnelles Wachstum, Hook-Tricks, Viral-Hacks,
Hustle, reißerische Versprechen, bezahlte Ads als Hauptthema.

AUFGABE: Erstelle einen kompakten Trend-Radar. Format:
- 1 kurzer Einstiegssatz (Marktbeobachtung dieser Woche)
- 3 bis 5 Trends/Themen als Stichpunkte, jeweils mit kurzer Einordnung warum es FÜR SABINES ZIELGRUPPE zählt
- 3 konkrete Content-Ideen (mit Plattform-Hinweis Instagram oder LinkedIn), die Sabine daraus machen kann

Wenn ein Thema nicht zu ihrer Brille passt, lass es weg. Lieber wenige relevante als viele beliebige.
Schreibe direkt an Sabine."""


def summarize(news_items: list[dict], ig_posts: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    quellen = "AKTUELLE SCHLAGZEILEN (Google News):\n"
    for n in news_items:
        quellen += f"- {n['title']} ({n['source']})\n"
    if ig_posts:
        quellen += "\nINSTAGRAM-BEITRÄGE (Hashtags):\n"
        for p in ig_posts:
            quellen += f"- {p['caption']} ({p['likes']} Likes)\n"

    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": quellen}],
    )
    return msg.content[0].text


# ── Telegram senden ──────────────────────────────────────────────────────────

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Telegram-Limit: 4096 Zeichen → ggf. aufteilen
    for i in range(0, len(text), 3800):
        chunk = text[i:i + 3800]
        with httpx.Client(timeout=20) as client:
            client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk})


# ── Hauptprogramm ─────────────────────────────────────────────────────────────

def main():
    log.info("Tägliche Inspiration startet …")

    news_items = []
    for kw in NEWS_KEYWORDS:
        news_items.extend(fetch_news(kw, limit=4))
    log.info("%d Schlagzeilen gefunden.", len(news_items))

    ig_posts = fetch_instagram(INSTAGRAM_HASHTAGS, limit=10)
    log.info("%d Instagram-Beiträge gefunden.", len(ig_posts))

    if not news_items and not ig_posts:
        send_telegram("Heute keine neuen Themen gefunden. (Quellen waren leer.)")
        return

    zusammenfassung = summarize(news_items, ig_posts)
    send_telegram("✨ Deine Inspiration für heute\n\n" + zusammenfassung)
    log.info("Gesendet. Fertig.")


if __name__ == "__main__":
    main()
