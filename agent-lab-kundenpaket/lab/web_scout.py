"""
web_scout.py — Woechentliche Recherche von AI-Quellen.

Durchsucht relevante Blogs und Quellen nach Neuerungen die fuer
Julias Agent-System relevant sind. Bewertet Relevanz und generiert
konkrete Empfehlungen.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import AgentConfig, run_agent
from .tracker import LabTracker

BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")

# Quellen und Suchbegriffe — AI + Content Research fuer Julias Nische
SOURCES = [
    # AI & Agent News
    {"name": "Anthropic Blog", "query": "site:anthropic.com/research OR site:anthropic.com/news"},
    {"name": "AI Agent Patterns", "query": "AI agent tool calling best practices 2026"},
    {"name": "Prompt Engineering", "query": "prompt engineering techniques system prompt 2026"},
    # Content Research — Julias Nische
    {"name": "Reddit Digital Products", "query": "site:reddit.com digital products selling online business 2026"},
    {"name": "Reddit Low Ticket", "query": "site:reddit.com low ticket offer mini course online business"},
    {"name": "Reddit KI Business", "query": "site:reddit.com AI tools online business automation solopreneur 2026"},
    {"name": "Threads Digital Products", "query": "site:threads.net digital products online business sell"},
    {"name": "Mini Apps Marketing", "query": "mini apps digital products marketing strategy 2026"},
    {"name": "Pinterest Marketing", "query": "Pinterest marketing digital products sell online 2026"},
    {"name": "YouTube Marketing", "query": "YouTube marketing digital products online course sell 2026"},
    {"name": "Instagram Reels Strategy", "query": "Instagram Reels strategy sell digital products 2026"},
    {"name": "Low Ticket Offers", "query": "low ticket offer funnel strategy digital products 2026"},
    # KI + Online Business
    {"name": "KI Digital Products", "query": "KI digitale Produkte erstellen online business 2026"},
    {"name": "AI Solopreneur", "query": "AI tools solopreneur automation online business replace team 2026"},
    {"name": "ChatGPT Business", "query": "ChatGPT online business course creator content automation 2026"},
    {"name": "AI Marketing Tools", "query": "AI marketing tools small business creator economy 2026"},
]

ANALYZE_PROMPT = """Du bist Julias Content Intelligence Analyst. Julia Trost hilft Menschen dabei, mit digitalen Produkten ein Online-Business aufzubauen. Ihre Nische: digitale Produkte, Minikurse, Online-Kurse, Funnels, Instagram Marketing.

Analysiere die folgenden Recherche-Ergebnisse und erstelle einen Content Intelligence Report mit genau diesen Abschnitten:

## 1. Top 10 brennende Fragen die Julias Zielgruppe gerade stellt
Die 10 wichtigsten Fragen die immer wieder auftauchen. Keine Dopplungen — jede Frage muss ein anderes Thema abdecken. Formuliere sie so, wie echte Menschen sie stellen wuerden.

## 2. Top 10 Frustrationen und Pain Points
Die 10 groessten Probleme. Jeder Punkt muss sich klar von den anderen unterscheiden — keine aehnlich klingenden Varianten.

## 3. Top 5 Trending Topics
Die 5 wichtigsten Trends und Gespraeche in der Nische gerade. Nur echte Trends, kein Fuellmaterial.

## 4. 5 Kontraere Content-Angles
5 gaengige Meinungen die Julia herausfordern kann. Jeder Angle muss provokant genug sein um Aufmerksamkeit zu erzeugen.

## 5. 15 hyper-spezifische Content-Ideen
Jede Idee muss ein konkretes Problem loesen und sich klar von den anderen unterscheiden. Format: Eine Zeile pro Idee, so spezifisch wie moeglich. Nicht "Wie du verkaufst" sondern "Wie du mit 500 Followern und einer Story-Sequenz taeglich 3 Verkaeufe machst". KEINE Dopplungen oder aehnlich klingende Ideen.

## 6. KI + Online Business — Fragen und Chancen
Was fragen sich die Leute gerade zum Thema KI im Online-Business? Welche Aengste und Chancen sehen sie? Z.B.: Ersetzt KI meinen Online-Kurs? Wie erstelle ich mit KI ein digitales Produkt? Brauche ich noch ein Team wenn ich KI habe? Kann KI meinen Content erstellen? Wie automatisiere ich mein Business mit KI?

## 7. AI/Agent-News fuer Julias System
Nur die relevantesten AI-Neuigkeiten die direkt auf Julias Agents anwendbar sind. Max 3-5 Punkte mit konkreter Empfehlung.

Antworte auf Deutsch. Sei ausfuehrlich und detailliert — lieber zu viel als zu wenig. Julias Zielgruppe sind Menschen die gerade erst starten ODER bereits ein kleines Online-Business haben und skalieren wollen. Viele davon interessieren sich auch fuer KI-Tools und wie sie KI fuer ihr Business nutzen koennen."""


def brave_search(query: str, num_results: int = 5) -> list[dict]:
    """Search via Brave API."""
    if not BRAVE_API_KEY:
        return []

    try:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": BRAVE_API_KEY, "Accept": "application/json"},
            params={"q": query, "count": num_results, "freshness": "pm"},  # past month
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("web", {}).get("results", [])
    except Exception:
        return []


class WebScout:
    """Weekly web research for AI improvements."""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        self._data_dir = Path(data_dir)
        self._tracker = LabTracker(data_dir=str(self._data_dir))

    def scout(self, verbose: bool = False) -> str:
        """Run weekly web research. Returns the analysis report."""
        if not BRAVE_API_KEY:
            return "Error: BRAVE_API_KEY nicht gesetzt."

        # 1. Search all sources
        print("  Durchsuche Quellen...")
        all_results = []
        for source in SOURCES:
            results = brave_search(source["query"], num_results=5)
            for r in results:
                all_results.append({
                    "source": source["name"],
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("description", ""),
                })

        if not all_results:
            return "Keine neuen Ergebnisse diese Woche."

        # 2. Build context
        context_parts = [f"## Neuigkeiten dieser Woche ({len(all_results)} Ergebnisse)\n"]
        for i, r in enumerate(all_results, 1):
            context_parts.append(
                f"[{i}] **{r['source']}**: {r['title']}\n"
                f"    {r['url']}\n"
                f"    {r['description']}\n"
            )

        context = "\n".join(context_parts)

        # 3. Analyze with Claude — in zwei Teilen fuer ausfuehrlichere Ergebnisse
        print("  Analysiere Teil 1 (Fragen, Pain Points, Trends, KI)...")
        prompt_part1 = """Erstelle die ersten 4 Abschnitte des Content Intelligence Reports:

## 1. Top 10 brennende Fragen (keine Dopplungen)
## 2. Top 10 Frustrationen und Pain Points (alle unterschiedlich)
## 3. Top 5 Trending Topics
## 6. KI + Online Business — Fragen und Chancen

Qualitaet vor Quantitaet. Keine redundanten oder aehnlich klingenden Punkte."""

        config1 = AgentConfig(
            model="claude-sonnet-4-6",
            system_prompt=ANALYZE_PROMPT,
            max_turns=3,
            max_tokens=6000,
        )

        part1 = run_agent(
            config=config1,
            tools=[],
            user_message=context + "\n\n" + prompt_part1,
            verbose=verbose,
        )

        print("  Analysiere Teil 2 (Angles, Content-Ideen, AI-News)...")
        prompt_part2 = """Erstelle die restlichen 3 Abschnitte des Content Intelligence Reports:

## 4. 5 Kontraere Content-Angles (provokant, auffallend)
## 5. 15 hyper-spezifische Content-Ideen (alle unterschiedlich, keine Dopplungen)
## 7. AI/Agent-News fuer Julias System

Qualitaet vor Quantitaet. Jede Content-Idee muss ein anderes konkretes Problem loesen."""

        config2 = AgentConfig(
            model="claude-sonnet-4-6",
            system_prompt=ANALYZE_PROMPT,
            max_turns=3,
            max_tokens=6000,
        )

        part2 = run_agent(
            config=config2,
            tools=[],
            user_message=context + "\n\n" + prompt_part2,
            verbose=verbose,
        )

        report = part1 + "\n\n---\n\n" + part2

        # 4. Save report
        date_str = time.strftime("%Y-%m-%d")
        report_path = self._data_dir / "research" / f"web-scout-{date_str}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            f"# Web Scout — {date_str}\n\n"
            f"Quellen: {', '.join(s['name'] for s in SOURCES)}\n"
            f"Ergebnisse: {len(all_results)}\n\n"
            f"---\n\n{report}",
            encoding="utf-8",
        )

        # 5. Log
        self._tracker.log("web_scout", {
            "description": f"Web Scout: {len(all_results)} Ergebnisse aus {len(SOURCES)} Quellen",
            "sources_searched": len(SOURCES),
            "results_found": len(all_results),
            "report_path": str(report_path),
        })

        return report
