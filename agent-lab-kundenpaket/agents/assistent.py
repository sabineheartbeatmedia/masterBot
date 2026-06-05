import os
import imaplib
import email
from email.header import decode_header
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ── Config ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

IONOS_EMAIL    = os.environ["IONOS_EMAIL"]
IONOS_PASSWORD = os.environ["IONOS_PASSWORD"]
IMAP_SERVER    = os.environ.get("IMAP_SERVER", "imap.ionos.de")
IMAP_PORT      = int(os.environ.get("IMAP_PORT", "993"))

GOOGLE_CLIENT_ID     = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]

# Farb-Nummern im Hauptkalender, die angezeigt werden sollen
# lila (Weintraube) = "3" = Heartbeat Media, blau (Heidelbeere) = "9" = SWX
HAUPTKALENDER_FARBEN = {"3": "Heartbeat Media", "9": "SWX"}
# Name (Teil davon) des zusätzlichen Kalenders, der komplett angezeigt wird
EXTRA_KALENDER_NAMEN = ["keep going", "alumni"]
# ─────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)

GOOGLE_COLOR_NAMES = {
    "1": "Lavendel", "2": "Salbei", "3": "Weintraube", "4": "Flamingo",
    "5": "Banane", "6": "Mandarine", "7": "Pfau", "8": "Grafit",
    "9": "Heidelbeere", "10": "Basilikum", "11": "Tomate",
}


# ── E-Mail (IONOS) ─────────────────────────────────────────────────────────

def _decode(value) -> str:
    if value is None:
        return ""
    parts = decode_header(value)
    out = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            out += text.decode(enc or "utf-8", errors="replace")
        else:
            out += text
    return out


def fetch_unread(limit: int = 10):
    mails = []
    total = 0
    imap = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    try:
        imap.login(IONOS_EMAIL, IONOS_PASSWORD)
        imap.select("INBOX")
        status, data = imap.search(None, "UNSEEN")
        if status != "OK":
            return [], 0
        ids = data[0].split()
        total = len(ids)
        for msg_id in reversed(ids[-limit:]):
            status, msg_data = imap.fetch(msg_id, "(BODY.PEEK[HEADER])")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            mails.append({
                "from":    _decode(msg.get("From")),
                "subject": _decode(msg.get("Subject")) or "(kein Betreff)",
                "date":    _decode(msg.get("Date")),
            })
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return mails, total


# ── Kalender (Google) ───────────────────────────────────────────────────────

def _calendar_service():
    creds = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _events_from_calendar(service, calendar_id, time_min, time_max):
    result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        maxResults=50,
    ).execute()
    return result.get("items", [])


def fetch_events(days: int = 7) -> list[dict]:
    """Holt: aus dem Hauptkalender nur farblich markierte Termine,
    aus dem Extra-Kalender (Keep Going/Alumni) alle Termine."""
    service = _calendar_service()
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days)).isoformat()

    events = []

    # 1) Hauptkalender – nur markierte Farben
    for ev in _events_from_calendar(service, "primary", time_min, time_max):
        color = ev.get("colorId")
        if color in HAUPTKALENDER_FARBEN:
            events.append({
                "summary": ev.get("summary", "(ohne Titel)"),
                "start":   ev["start"].get("dateTime", ev["start"].get("date")),
                "all_day": "date" in ev["start"],
                "tag":     HAUPTKALENDER_FARBEN[color],
            })

    # 2) Extra-Kalender finden und komplett einlesen
    cal_list = service.calendarList().list().execute().get("items", [])
    for cal in cal_list:
        name = (cal.get("summary") or "").lower()
        if any(teil in name for teil in EXTRA_KALENDER_NAMEN):
            for ev in _events_from_calendar(service, cal["id"], time_min, time_max):
                events.append({
                    "summary": ev.get("summary", "(ohne Titel)"),
                    "start":   ev["start"].get("dateTime", ev["start"].get("date")),
                    "all_day": "date" in ev["start"],
                    "tag":     cal.get("summary", "Extra"),
                })

    # nach Startzeit sortieren
    events.sort(key=lambda e: e["start"])
    return events


def _format_start(start_iso: str, all_day: bool) -> str:
    try:
        d = datetime.fromisoformat(start_iso)
        if all_day:
            return d.strftime("%a %d.%m.") + " (ganztägig)"
        return d.strftime("%a %d.%m. um %H:%M")
    except Exception:
        return start_iso


# ── Telegram Befehle ───────────────────────────────────────────────────────

def _authorized(update: Update) -> bool:
    return str(update.effective_chat.id) == str(TELEGRAM_CHAT_ID)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    await update.message.reply_text(
        "👋 Hallo Sabine!\n\n"
        "Ich bin dein persönlicher Assistent.\n\n"
        "Befehle:\n"
        "/mails – deine neuesten ungelesenen Mails\n"
        "/termine – Heartbeat Media, SWX & Keep Going Termine (7 Tage)\n"
        "/start – diese Hilfe"
    )


async def mails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    await update.message.reply_text("📭 Schaue nach …")
    try:
        unread, total = fetch_unread(limit=10)
    except Exception as e:
        log.error("IMAP-Fehler: %s", e)
        await update.message.reply_text("❌ Konnte das Postfach nicht abrufen.")
        return

    if not unread:
        await update.message.reply_text("✅ Keine ungelesenen Mails. Alles erledigt!")
        return

    lines = [f"📧 *{total} ungelesene Mail(s) gesamt* (zeige die neuesten {len(unread)}):\n"]
    for m in unread:
        lines.append(
            f"✉️ *{m['subject']}*\n"
            f"   von: {m['from']}\n"
            f"   {m['date']}\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def termine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    await update.message.reply_text("📅 Schaue in deinen Kalender …")
    try:
        events = fetch_events(days=7)
    except Exception as e:
        log.error("Kalender-Fehler: %s", e)
        await update.message.reply_text("❌ Konnte den Kalender nicht abrufen.")
        return

    if not events:
        await update.message.reply_text(
            "✅ Keine passenden Termine in den nächsten 7 Tagen."
        )
        return

    lines = [f"📅 *Deine nächsten {len(events)} Termine:*\n"]
    for ev in events:
        lines.append(
            f"🗓️ *{ev['summary']}*  _({ev['tag']})_\n"
            f"   {_format_start(ev['start'], ev['all_day'])}\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mails", mails))
    app.add_handler(CommandHandler("termine", termine))
    log.info("Assistent-Bot gestartet. Warte auf Befehle …")
    app.run_polling()


if __name__ == "__main__":
    main()
