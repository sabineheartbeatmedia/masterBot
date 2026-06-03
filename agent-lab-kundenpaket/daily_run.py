"""
daily_run.py — Taeglicher Agent Lab Zyklus.

Ablauf:
1. Agents scannen
2. Performance-Daten + Sources recherchieren
3. Relevanz bewerten, Empfehlungen generieren
4. Reaktive Fixes auto-applyen (minor)
5. Proaktive Aenderungen in Queue (major)
6. Report via Telegram senden

Wird per Cron taeglich ausgefuehrt.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

from lab.scanner import AgentScanner
from lab.researcher import Researcher
from lab.analyzer import Analyzer
from lab.applier import Applier
from lab.tracker import LabTracker
from lab.bloat_monitor import BloatMonitor

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def send_telegram(text: str):
    """Send a message via Telegram Bot API."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[Telegram nicht konfiguriert] {text[:200]}")
        return

    # Split long messages (Telegram limit: 4096 chars)
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]

    for chunk in chunks:
        data = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown",
        }).encode("utf-8")

        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        try:
            urllib.request.urlopen(req)
        except Exception as e:
            # Retry without markdown if parsing fails
            data = json.dumps({
                "chat_id": TELEGRAM_CHAT_ID,
                "text": chunk,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            try:
                urllib.request.urlopen(req)
            except Exception:
                print(f"[Telegram Fehler] {e}")


def daily_cycle():
    """Run the complete daily cycle."""
    start = time.time()
    report_lines = ["🧪 *Agent Lab — Tagesbericht*", f"📅 {time.strftime('%Y-%m-%d %H:%M')}", ""]

    scanner = AgentScanner()
    researcher = Researcher()
    analyzer = Analyzer(data_dir=DATA_DIR)
    applier = Applier(data_dir=DATA_DIR)
    tracker = LabTracker(data_dir=DATA_DIR)

    # 1. Scan
    print("1/5 Scanning agents...")
    snapshots = scanner.scan_all()
    report_lines.append(f"*Scan:* {len(snapshots)} Agents gefunden")
    tracker.log("daily_scan", {"agents": len(snapshots)})

    # 2. Research
    print("2/5 Researching improvements...")
    try:
        research_report = researcher.run_research()
        report_lines.append("*Research:* Abgeschlossen")
    except Exception as e:
        research_report = ""
        report_lines.append(f"*Research:* Fehler — {str(e)[:80]}")

    # 3. Analyze
    print("3/5 Analyzing and scoring...")
    if research_report:
        improvements = analyzer.analyze(research_report)
        report_lines.append(f"*Analyse:* {len(improvements)} Verbesserungen identifiziert")
    else:
        improvements = []
        report_lines.append("*Analyse:* Uebersprungen (keine Research-Daten)")

    # 4. Auto-apply reactive (minor) + queue proactive (major)
    print("4/5 Processing improvements...")
    auto_applied = []
    queued = []

    for imp in improvements:
        result = applier.process(imp)
        if imp.severity == "minor" and imp.status == "applied":
            auto_applied.append(imp)
        else:
            queued.append(imp)

    if auto_applied:
        report_lines.append("")
        report_lines.append(f"*Auto-applied ({len(auto_applied)}):*")
        for imp in auto_applied:
            report_lines.append(f"  🔧 {imp.agent_name}: {imp.description[:60]}")

    if queued:
        report_lines.append("")
        report_lines.append(f"*Warten auf Approval ({len(queued)}):*")
        for imp in queued:
            icon = "⚠️" if imp.severity == "major" else "🔧"
            report_lines.append(f"  {icon} {imp.agent_name}: {imp.description[:60]}")
        report_lines.append("")
        report_lines.append("→ /queue im Agent Lab Bot zum Reviewen")

    # 5. Bloat Monitor
    print("5/6 Checking skill bloat...")
    monitor = BloatMonitor(scanner)
    flagged = [r for r in monitor.check_all() if r.level != "ok"]
    if flagged:
        report_lines.append("")
        report_lines.append("*Skill Bloat Monitor:*")
        for r in flagged:
            icon = "🔴" if r.level == "critical" else "🟡"
            report_lines.append(f"  {icon} {r.agent_name}: {r.tool_count} Tools")
            report_lines.append(f"     {r.recommendation[:80]}")

    # 6. Summary
    duration = time.time() - start
    report_lines.append("")
    report_lines.append(f"⏱ Dauer: {duration:.0f}s")

    # Load overall queue size
    total_queue = len(applier.get_queue())
    if total_queue > 0:
        report_lines.append(f"📋 Queue gesamt: {total_queue} offene Items")

    report = "\n".join(report_lines)

    # 6. Send report
    print("6/6 Sending report...")
    send_telegram(report)
    print(report)

    tracker.log("daily_run", {
        "description": f"Tagesrun: {len(improvements)} Improvements, {len(auto_applied)} auto-applied, {len(queued)} queued",
        "duration_seconds": round(duration),
        "improvements": len(improvements),
        "auto_applied": len(auto_applied),
        "queued": len(queued),
    })

    return report


if __name__ == "__main__":
    daily_cycle()
