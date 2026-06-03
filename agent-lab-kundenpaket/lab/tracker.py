"""
tracker.py — Activity Log fuer Agent Lab.

Loggt alle Aktionen: Scans, Research, Improvements, Applies, Approvals.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional


class LabTracker:
    """Logs all Agent Lab activity to a JSON file."""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self._log_file = Path(data_dir) / "lab-log.json"
        self._entries: list[dict] = []
        self._load()

    def _load(self):
        if self._log_file.exists():
            try:
                self._entries = json.loads(self._log_file.read_text())
            except (json.JSONDecodeError, OSError):
                self._entries = []

    def _save(self):
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        self._log_file.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2)
        )

    def log(self, action: str, details: dict = None):
        entry = {
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "details": details or {},
        }
        self._entries.append(entry)
        self._save()

    def get_recent(self, n: int = 20) -> list[dict]:
        return self._entries[-n:]

    def get_summary(self) -> str:
        if not self._entries:
            return "Noch keine Aktivitaeten."

        lines = [f"Agent Lab — {len(self._entries)} Aktionen gesamt", ""]

        # Count by action type
        by_action: dict[str, int] = {}
        for e in self._entries:
            a = e["action"]
            by_action[a] = by_action.get(a, 0) + 1

        for action, count in sorted(by_action.items()):
            lines.append(f"  {action}: {count}x")

        # Last 5 entries
        lines.append("")
        lines.append("Letzte Aktionen:")
        for e in self._entries[-5:]:
            desc = e.get("details", {}).get("description", "")
            lines.append(f"  [{e['time_str']}] {e['action']}: {desc[:60]}")

        return "\n".join(lines)
