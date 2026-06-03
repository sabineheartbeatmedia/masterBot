"""
analyzer.py — Parst Research-Ergebnisse in strukturierte Improvements.

Nimmt den Research-Report und extrahiert konkrete, anwendbare Verbesserungen.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import AgentConfig, run_agent
from .tracker import LabTracker


@dataclass
class Improvement:
    id: str
    agent_name: str
    category: str       # prompt, keywords, config, tool
    severity: str       # minor, major
    description: str
    diff: str           # Vorher → Nachher
    source: str         # research report date or manual
    status: str = "new" # new, queued, applied, rejected
    created_at: str = ""

    def summary(self) -> str:
        icon = "🔧" if self.severity == "minor" else "⚠️"
        return f"{icon} [{self.id[:8]}] {self.agent_name} ({self.category}): {self.description[:80]}"


ANALYZE_PROMPT = """Du bist ein strukturierter Parser. Extrahiere aus dem folgenden Research-Report alle konkreten Verbesserungsvorschlaege.

Fuer JEDEN Vorschlag, gib ein JSON-Objekt aus mit exakt diesen Feldern:
- agent_name: string (Name des betroffenen Agents)
- category: "prompt" | "keywords" | "config" | "tool"
- severity: "minor" | "major"
- description: string (kurze Beschreibung)
- diff: string (Vorher → Nachher, so konkret wie moeglich)

Antworte NUR mit einem JSON-Array von Objekten. Kein anderer Text.

Beispiel:
```json
[
  {
    "agent_name": "mein_agent",
    "category": "keywords",
    "severity": "minor",
    "description": "Keyword 'onlinekurs' fehlt",
    "diff": "keywords hinzufuegen: 'onlinekurs', 'webinar'"
  }
]
```"""


class Analyzer:
    """Analyzes research reports and extracts structured improvements."""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        self._data_dir = Path(data_dir)
        self._tracker = LabTracker(data_dir=str(self._data_dir))

    def analyze(self, research_report: str, verbose: bool = False) -> list[Improvement]:
        """Parse a research report into structured improvements."""
        config = AgentConfig(
            model="claude-sonnet-4-6",
            system_prompt=ANALYZE_PROMPT,
            max_turns=3,
            max_tokens=3000,
        )

        response = run_agent(
            config=config,
            tools=[],
            user_message=f"Research-Report:\n\n{research_report}",
            verbose=verbose,
        )

        improvements = self._parse_response(response)

        # Save improvements
        for imp in improvements:
            self._save_improvement(imp)

        self._tracker.log("analyze", {
            "description": f"{len(improvements)} Verbesserungen identifiziert",
            "improvements": [imp.id[:8] for imp in improvements],
        })

        return improvements

    def analyze_latest(self, verbose: bool = False) -> list[Improvement]:
        """Analyze the most recent research report."""
        research_dir = self._data_dir / "research"
        if not research_dir.exists():
            return []

        reports = sorted(research_dir.glob("*.md"), reverse=True)
        if not reports:
            return []

        report_content = reports[0].read_text(encoding="utf-8")
        return self.analyze(report_content, verbose=verbose)

    def _parse_response(self, response: str) -> list[Improvement]:
        """Extract JSON array from LLM response."""
        # Find JSON array in response
        import re
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if not json_match:
            return []

        try:
            raw_items = json.loads(json_match.group())
        except json.JSONDecodeError:
            return []

        improvements = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            imp = Improvement(
                id=str(uuid.uuid4()),
                agent_name=item.get("agent_name", "unknown"),
                category=item.get("category", "prompt"),
                severity=item.get("severity", "major"),
                description=item.get("description", ""),
                diff=item.get("diff", ""),
                source=time.strftime("%Y-%m-%d"),
                created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            improvements.append(imp)

        return improvements

    def _save_improvement(self, imp: Improvement):
        """Save improvement as JSON file."""
        imp_dir = self._data_dir / "improvements"
        imp_dir.mkdir(parents=True, exist_ok=True)
        path = imp_dir / f"{imp.id[:8]}_{imp.agent_name}.json"
        path.write_text(json.dumps(asdict(imp), ensure_ascii=False, indent=2))

    def get_all_improvements(self) -> list[Improvement]:
        """Load all saved improvements."""
        imp_dir = self._data_dir / "improvements"
        if not imp_dir.exists():
            return []

        improvements = []
        for f in sorted(imp_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                improvements.append(Improvement(**data))
            except (json.JSONDecodeError, TypeError):
                continue
        return improvements
