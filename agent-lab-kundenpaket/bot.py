"""
Agent Lab Telegram Bot — Approval-Interface fuer Julia.

Zeigt Verbesserungsvorschlaege, erlaubt Approve/Reject,
und informiert proaktiv ueber Auto-Applies.

Starten: python bot.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime
import pytz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode

from lab.scanner import AgentScanner
from lab.researcher import Researcher
from lab.analyzer import Analyzer
from lab.applier import Applier
from lab.tracker import LabTracker
from lab.bloat_monitor import BloatMonitor
from lab.web_scout import WebScout

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

scanner = AgentScanner()
researcher = Researcher()
analyzer = Analyzer(data_dir=DATA_DIR)
applier = Applier(data_dir=DATA_DIR)
tracker = LabTracker(data_dir=DATA_DIR)

bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    agents = scanner.scan_all()
    queue = applier.get_queue()

    await message.answer(
        f"🧪 *Agent Lab*\n\n"
        f"Meta-Agent der deine {len(agents)} Agents verbessert.\n\n"
        f"Offene Queue: {len(queue)} Items\n\n"
        f"Commands:\n"
        f"  /status — Alle Agents anzeigen\n"
        f"  /queue — Offene Aenderungen\n"
        f"  /approve <id> — Genehmigen\n"
        f"  /reject <id> — Ablehnen\n"
        f"  /scan — Agents jetzt scannen\n"
        f"  /research — Research jetzt starten\n"
        f"  /run — Kompletter Zyklus\n"
        f"  /scout — Web Scout jetzt starten\n"
        f"  /bloat — Skill Bloat Check\n"
        f"  /log — Letzte Aktionen",
        parse_mode=ParseMode.MARKDOWN,
    )


@dp.message(Command("status"))
async def cmd_status(message: Message):
    agents = scanner.scan_all()
    lines = [f"*{len(agents)} Agents gefunden:*\n"]
    for s in agents:
        tools = ", ".join(s.tools) if s.tools else "keine"
        lines.append(f"*{s.name}*\n  Model: {s.model or '?'} | Turns: {s.max_turns} | Tools: {tools}")
    await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("queue"))
async def cmd_queue(message: Message):
    queue = applier.get_queue()
    if not queue:
        await message.answer("Queue ist leer.")
        return

    lines = [f"*{len(queue)} offene Aenderungen:*\n"]
    for imp in queue:
        icon = "🔧" if imp.severity == "minor" else "⚠️"
        lines.append(
            f"{icon} `{imp.id[:8]}` — *{imp.agent_name}* ({imp.category})\n"
            f"  {imp.description[:100]}\n"
            f"  /approve {imp.id[:8]} | /reject {imp.id[:8]}"
        )
    await message.answer("\n\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("approve"))
async def cmd_approve(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Verwendung: /approve <id>")
        return
    result = applier.approve(args[1].strip())
    await message.answer(result)


@dp.message(Command("reject"))
async def cmd_reject(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Verwendung: /reject <id>")
        return
    result = applier.reject(args[1].strip())
    await message.answer(result)


@dp.message(Command("scan"))
async def cmd_scan(message: Message):
    await message.answer("Scanne Agents...")
    agents = await asyncio.to_thread(scanner.scan_all)
    tracker.log("scan", {"description": f"{len(agents)} Agents gescannt"})
    lines = [f"{len(agents)} Agents gefunden:"]
    for s in agents:
        lines.append(f"  {s.name} — {s.model or '?'}, {len(s.keywords)} Keywords")
    await message.answer("\n".join(lines))


@dp.message(Command("research"))
async def cmd_research(message: Message):
    await message.answer("Starte Research... (dauert ca. 30 Sekunden)")
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    report = await asyncio.to_thread(researcher.run_research)

    # Truncate for Telegram
    if len(report) > 4000:
        report = report[:4000] + "\n\n... (gekuerzt)"
    await message.answer(report)


@dp.message(Command("run"))
async def cmd_run(message: Message):
    await message.answer("Starte kompletten Zyklus: Scan → Research → Analyze...")
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Scan
    agents = await asyncio.to_thread(scanner.scan_all)
    await message.answer(f"Scan: {len(agents)} Agents gefunden.")

    # Research
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    report = await asyncio.to_thread(researcher.run_research)
    await message.answer(f"Research abgeschlossen. Analysiere...")

    # Analyze + Process
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    improvements = await asyncio.to_thread(analyzer.analyze, report)

    if not improvements:
        await message.answer("Keine Verbesserungen gefunden.")
        return

    results = []
    for imp in improvements:
        result = applier.process(imp)
        results.append(f"{imp.summary()}\n  → {result}")

    await message.answer(
        f"*{len(improvements)} Verbesserungen verarbeitet:*\n\n" + "\n\n".join(results),
        parse_mode=ParseMode.MARKDOWN,
    )

    # Show queue
    queue = applier.get_queue()
    if queue:
        await message.answer(f"{len(queue)} Items warten auf dein Approval. Schreib /queue")


@dp.message(Command("scout"))
async def cmd_scout(message: Message):
    await message.answer("Durchsuche AI- und Content-Quellen... (dauert ca. 60-90 Sekunden)")
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    scout = WebScout()
    report = await asyncio.to_thread(scout.scout)
    # In mehrere Nachrichten aufteilen (Telegram-Limit: 4096 Zeichen)
    for i in range(0, len(report), 4000):
        chunk = report[i:i + 4000]
        await message.answer(chunk)


@dp.message(Command("bloat"))
async def cmd_bloat(message: Message):
    monitor = BloatMonitor(scanner)
    summary = monitor.get_summary()
    await message.answer(summary)


@dp.message(Command("log"))
async def cmd_log(message: Message):
    summary = tracker.get_summary()
    await message.answer(f"```\n{summary}\n```", parse_mode=ParseMode.MARKDOWN)


# --- Weekly Auto-Run ---

BERLIN_TZ = pytz.timezone("Europe/Berlin")
WEEKLY_DAY = int(os.environ.get("WEEKLY_DAY", "0"))  # 0=Montag
WEEKLY_HOUR = int(os.environ.get("WEEKLY_HOUR", "7"))
WEEKLY_MINUTE = int(os.environ.get("WEEKLY_MINUTE", "0"))
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6199076480")


async def weekly_scheduler():
    """Fuehrt jeden Montag um 7:00 den Agent Lab Zyklus aus."""
    logger.info(f"Weekly Scheduler aktiv — Laeuft jeden Montag um {WEEKLY_HOUR:02d}:{WEEKLY_MINUTE:02d} (Berlin)")
    sent_this_week = False

    while True:
        now = datetime.now(BERLIN_TZ)

        if now.weekday() == WEEKLY_DAY and now.hour == WEEKLY_HOUR and now.minute == WEEKLY_MINUTE and not sent_this_week:
            logger.info("Starte woechentlichen Agent Lab Zyklus...")
            await bot.send_message(chat_id=CHAT_ID, text="🧪 Agent Lab — Woechentlicher Scan startet...")

            try:
                from daily_run import daily_cycle
                report = await asyncio.to_thread(daily_cycle)
                logger.info("Woechentlicher Zyklus abgeschlossen.")
            except Exception as e:
                logger.error(f"Weekly cycle error: {e}")
                await bot.send_message(chat_id=CHAT_ID, text=f"Agent Lab Fehler: {e}")

            sent_this_week = True

        # Reset am Dienstag
        if now.weekday() != WEEKLY_DAY:
            sent_this_week = False

        await asyncio.sleep(30)


async def main():
    logger.info("Agent Lab Bot gestartet.")
    asyncio.create_task(weekly_scheduler())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
