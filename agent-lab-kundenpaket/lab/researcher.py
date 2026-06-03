"""
researcher.py — Recherchiert AI-Verbesserungen aus drei Quellen:

1. Performance-Daten (Tracker) — welcher Agent wie oft, Kosten, Effizienz
2. Agent-Analyse — System-Prompt-Qualitaet, fehlende Keywords, Config-Probleme
3. Web Search — AI News, Prompt Engineering Best Practices (wenn BRAVE_API_KEY vorhanden)

Speichert Ergebnisse als Markdown in data/research/.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import AgentConfig, run_agent
from agent.tool_registry import Tool

from .scanner import AgentScanner, AgentSnapshot
from .tracker import LabTracker


RESEARCH_PROMPT = """Du bist ein AI-Agent-Spezialist. Analysiere die folgenden Agent-Konfigurationen und Performance-Daten.

Identifiziere konkrete Verbesserungsmoeglichkeiten in diesen Kategorien:
1. **System-Prompts** — Sind sie klar, konsistent, vollstaendig? Fehlen wichtige Anweisungen?
2. **Keywords** — Fehlen offensichtliche Keywords fuer das Routing?
3. **Config** — Sind max_turns, max_tokens, model sinnvoll gewaehlt?
4. **Allgemein** — Gibt es Best Practices die nicht umgesetzt sind?

Fuer JEDE Verbesserung, gib an:
- **Agent:** Welcher Agent betroffen ist
- **Kategorie:** prompt / keywords / config / tool
- **Schwere:** minor (Tippfehler, fehlende Keywords) oder major (inhaltliche Prompt-Aenderung)
- **Beschreibung:** Was genau geaendert werden soll und warum
- **Vorher/Nachher:** Konkreter Diff wenn moeglich

Antworte auf Deutsch. Sei konkret, nicht vage."""


class Researcher:
    """Researches AI improvements for existing agents."""

    def __init__(self, vault_root: str = None, data_dir: str = None):
        if vault_root is None:
            vault_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), "..", "data")

        self._vault_root = vault_root
        self._data_dir = Path(data_dir)
        self._scanner = AgentScanner(vault_root=vault_root)
        self._tracker = LabTracker(data_dir=str(self._data_dir))

    def run_research(self, verbose: bool = False) -> str:
        """Run full research cycle. Returns the research report as string."""
        # 1. Scan agents
        snapshots = self._scanner.scan_all()
        if not snapshots:
            return "Keine Agents gefunden."

        # 2. Load performance data
        perf_data = self._load_performance_data()

        # 3. Build context for the research agent
        context = self._build_context(snapshots, perf_data)

        # 4. Run research agent
        config = AgentConfig(
            model="claude-sonnet-4-6",
            system_prompt=RESEARCH_PROMPT,
            max_turns=5,
            max_tokens=4000,
        )

        report = run_agent(
            config=config,
            tools=[],
            user_message=context,
            verbose=verbose,
        )

        # 5. Save research report
        date_str = time.strftime("%Y-%m-%d")
        report_path = self._data_dir / "research" / f"{date_str}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            f"# Agent Lab Research — {date_str}\n\n{report}",
            encoding="utf-8",
        )

        # 6. Log
        self._tracker.log("research", {
            "description": f"Research durchgefuehrt, {len(snapshots)} Agents analysiert",
            "agents_scanned": [s.name for s in snapshots],
            "report_path": str(report_path),
        })

        return report

    def _load_performance_data(self) -> str:
        """Load tracker data from the telegram orchestrator."""
        tracker_path = Path(self._vault_root) / "04-projects" / "telegram-orchestrator" / "tracker_data.json"
        if not tracker_path.exists():
            return "Keine Performance-Daten vorhanden (tracker_data.json nicht gefunden)."

        try:
            data = json.loads(tracker_path.read_text())
        except (json.JSONDecodeError, OSError):
            return "Performance-Daten konnten nicht gelesen werden."

        if not data:
            return "Noch keine Aufrufe aufgezeichnet."

        # Aggregate stats
        total = len(data)
        total_cost = sum(e.get("cost_eur", 0) for e in data)

        by_agent: dict[str, dict] = {}
        for e in data:
            name = e.get("agent_name", "unknown")
            if name not in by_agent:
                by_agent[name] = {"count": 0, "cost": 0.0, "routing": {}}
            by_agent[name]["count"] += 1
            by_agent[name]["cost"] += e.get("cost_eur", 0)
            method = e.get("routing_method", "unknown")
            by_agent[name]["routing"][method] = by_agent[name]["routing"].get(method, 0) + 1

        lines = [
            f"Performance-Daten: {total} Aufrufe, {total_cost:.4f}€ Gesamtkosten",
            "",
        ]
        for name, stats in by_agent.items():
            routing_str = ", ".join(f"{m}: {c}x" for m, c in stats["routing"].items())
            lines.append(f"  {name}: {stats['count']}x ({stats['cost']:.4f}€) — Routing: {routing_str}")

        return "\n".join(lines)

    def _build_context(self, snapshots: list[AgentSnapshot], perf_data: str) -> str:
        """Build the full context string for the research agent."""
        parts = ["## Aktuelle Agent-Konfigurationen\n"]

        for s in snapshots:
            parts.append(f"### {s.name}")
            parts.append(f"**Datei:** `{s.file_path}`")
            parts.append(f"**Model:** {s.model or '(nicht gesetzt)'}")
            parts.append(f"**Max Turns:** {s.max_turns}, **Max Tokens:** {s.max_tokens}")
            parts.append(f"**Tools:** {', '.join(s.tools) or '(keine)'}")
            parts.append(f"**Keywords ({len(s.keywords)}):** {', '.join(s.keywords[:15])}{'...' if len(s.keywords) > 15 else ''}")
            parts.append(f"\n**System-Prompt:**\n```\n{s.system_prompt[:2000]}\n```\n")

        parts.append("## Performance-Daten\n")
        parts.append(perf_data)

        return "\n".join(parts)
