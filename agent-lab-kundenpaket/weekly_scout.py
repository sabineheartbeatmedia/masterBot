"""
weekly_scout.py — Woechentlicher Web-Scout.

Durchsucht AI-Quellen nach Neuerungen und schickt
einen Bericht mit konkreten Empfehlungen via Telegram.

Wird per Cron woechentlich ausgefuehrt (Montags).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

from daily_run import send_telegram
from lab.web_scout import WebScout
from lab.tracker import LabTracker

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def weekly_cycle():
    start = time.time()
    tracker = LabTracker(data_dir=DATA_DIR)
    scout = WebScout(data_dir=DATA_DIR)

    print("Web Scout startet...")
    report = scout.scout()

    duration = time.time() - start

    # Build Telegram message
    header = (
        f"🔍 *Web Scout — Wochenbericht*\n"
        f"📅 {time.strftime('%Y-%m-%d')}\n"
        f"⏱ {duration:.0f}s\n\n"
    )

    send_telegram(header + report)
    print(header + report)

    tracker.log("weekly_scout", {
        "description": f"Woechentlicher Web Scout abgeschlossen",
        "duration_seconds": round(duration),
    })


if __name__ == "__main__":
    weekly_cycle()
