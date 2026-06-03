"""
Agent Lab CLI — Meta-Agent der andere Agents verbessert.

Verwendung:
    python lab.py scan           # Alle Agents scannen
    python lab.py research       # AI-Verbesserungen recherchieren
    python lab.py analyze        # Verbesserungen aus Research extrahieren
    python lab.py queue          # Offene Approval-Queue anzeigen
    python lab.py approve <id>   # Aenderung genehmigen
    python lab.py reject <id>    # Aenderung ablehnen
    python lab.py log            # Letzte Aktionen anzeigen
    python lab.py run            # Kompletter Zyklus
    python lab.py run --verbose  # Mit Debug-Output
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)

from lab.scanner import AgentScanner
from lab.researcher import Researcher
from lab.analyzer import Analyzer
from lab.applier import Applier
from lab.tracker import LabTracker


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def cmd_scan():
    scanner = AgentScanner()
    snapshots = scanner.scan_all()
    print(f"=== Agent Scan: {len(snapshots)} Agents gefunden ===\n")
    for s in snapshots:
        print(s.summary())
        print()


def cmd_research(verbose: bool = False):
    researcher = Researcher()
    print("Recherchiere Verbesserungen...\n")
    report = researcher.run_research(verbose=verbose)
    print("=== Research Report ===\n")
    print(report)


def cmd_analyze(verbose: bool = False):
    analyzer = Analyzer(data_dir=DATA_DIR)
    print("Analysiere letzten Research-Report...\n")
    improvements = analyzer.analyze_latest(verbose=verbose)

    if not improvements:
        print("Keine Verbesserungen gefunden.")
        return

    applier = Applier(data_dir=DATA_DIR)
    print(f"=== {len(improvements)} Verbesserungen gefunden ===\n")

    for imp in improvements:
        print(imp.summary())
        result = applier.process(imp)
        print(f"  → {result}\n")


def cmd_queue():
    applier = Applier(data_dir=DATA_DIR)
    queue = applier.get_queue()

    if not queue:
        print("Queue ist leer. Keine offenen Aenderungen.")
        return

    print(f"=== Approval Queue: {len(queue)} Items ===\n")
    for imp in queue:
        print(imp.summary())
        print(f"  Diff: {imp.diff[:100]}")
        print(f"  ID: {imp.id[:8]}")
        print()


def cmd_approve(improvement_id: str):
    applier = Applier(data_dir=DATA_DIR)
    result = applier.approve(improvement_id)
    print(result)


def cmd_reject(improvement_id: str):
    applier = Applier(data_dir=DATA_DIR)
    result = applier.reject(improvement_id)
    print(result)


def cmd_log():
    tracker = LabTracker(data_dir=DATA_DIR)
    print(tracker.get_summary())


def cmd_run(verbose: bool = False):
    print("=== Agent Lab: Kompletter Zyklus ===\n")

    print("1/3 Scanning Agents...")
    cmd_scan()

    print("\n2/3 Researching improvements...")
    cmd_research(verbose=verbose)

    print("\n3/3 Analyzing and processing...")
    cmd_analyze(verbose=verbose)

    print("\n=== Zyklus abgeschlossen ===")
    cmd_queue()


def main():
    verbose = "--verbose" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        print(__doc__)
        return

    cmd = args[0]

    if cmd == "scan":
        cmd_scan()
    elif cmd == "research":
        cmd_research(verbose=verbose)
    elif cmd == "analyze":
        cmd_analyze(verbose=verbose)
    elif cmd == "queue":
        cmd_queue()
    elif cmd == "approve" and len(args) > 1:
        cmd_approve(args[1])
    elif cmd == "reject" and len(args) > 1:
        cmd_reject(args[1])
    elif cmd == "log":
        cmd_log()
    elif cmd == "run":
        cmd_run(verbose=verbose)
    else:
        print(f"Unbekannter Command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
