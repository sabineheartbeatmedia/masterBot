"""
bloat_monitor.py — Ueberwacht Skill/Tool-Bloat in Agents.

Regeln:
- 1-4 Tools: OK
- 5-7 Tools: Warning (flaggen)
- 8+  Tools: Recommend splitting into sub-agents
"""
from __future__ import annotations

from dataclasses import dataclass
from .scanner import AgentScanner, AgentSnapshot


WARN_THRESHOLD = 5
SPLIT_THRESHOLD = 8


@dataclass
class BloatReport:
    agent_name: str
    tool_count: int
    tools: list[str]
    level: str       # "ok", "warning", "critical"
    recommendation: str


class BloatMonitor:
    """Monitors agent tool counts and flags bloat."""

    def __init__(self, scanner: AgentScanner = None):
        self._scanner = scanner or AgentScanner()

    def check_all(self) -> list[BloatReport]:
        snapshots = self._scanner.scan_all()
        return [self._check(s) for s in snapshots]

    def check_one(self, name: str) -> BloatReport | None:
        snapshot = self._scanner.scan_one(name)
        if snapshot:
            return self._check(snapshot)
        return None

    def _check(self, snapshot: AgentSnapshot) -> BloatReport:
        count = len(snapshot.tools)

        if count >= SPLIT_THRESHOLD:
            level = "critical"
            recommendation = (
                f"{snapshot.name} hat {count} Tools — zu viele fuer einen Agent. "
                f"Empfehlung: In Sub-Agents aufteilen. Gruppiere verwandte Tools "
                f"in spezialisierte Agents und nutze SubAgentTool fuer Delegation."
            )
        elif count >= WARN_THRESHOLD:
            level = "warning"
            recommendation = (
                f"{snapshot.name} hat {count} Tools — wird unuebersichtlich. "
                f"Beobachten und bei weiterem Wachstum aufteilen."
            )
        else:
            level = "ok"
            recommendation = ""

        return BloatReport(
            agent_name=snapshot.name,
            tool_count=count,
            tools=snapshot.tools,
            level=level,
            recommendation=recommendation,
        )

    def get_summary(self) -> str:
        reports = self.check_all()
        flagged = [r for r in reports if r.level != "ok"]

        if not flagged:
            lines = ["Skill Bloat Monitor: Alles OK", ""]
            for r in reports:
                lines.append(f"  {r.agent_name}: {r.tool_count} Tools ✓")
            return "\n".join(lines)

        lines = ["Skill Bloat Monitor:", ""]
        for r in reports:
            if r.level == "critical":
                icon = "🔴"
            elif r.level == "warning":
                icon = "🟡"
            else:
                icon = "✅"

            line = f"  {icon} {r.agent_name}: {r.tool_count} Tools"
            if r.tools:
                line += f" ({', '.join(r.tools)})"
            lines.append(line)

            if r.recommendation:
                lines.append(f"     → {r.recommendation}")

        return "\n".join(lines)
