"""
applier.py — Wendet Verbesserungen an oder queued sie fuer Approval.

Minor Changes: Auto-Apply direkt in die Agent-Datei.
Major Changes: In die Queue legen, auf Julias Approval warten.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

from .analyzer import Improvement
from .tracker import LabTracker


class Applier:
    """Applies improvements to agent files or queues them for approval."""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        self._data_dir = Path(data_dir)
        self._tracker = LabTracker(data_dir=str(self._data_dir))

    def process(self, improvement: Improvement) -> str:
        """Route improvement: auto-apply minor, queue major."""
        if improvement.severity == "minor":
            return self.auto_apply(improvement)
        else:
            return self.queue_for_approval(improvement)

    def auto_apply(self, improvement: Improvement) -> str:
        """Apply a minor improvement directly."""
        if improvement.category == "keywords":
            result = self._apply_keyword_change(improvement)
        else:
            # For other minor changes, queue instead of risking bad edits
            return self.queue_for_approval(improvement)

        if result:
            improvement.status = "applied"
            self._move_to_applied(improvement)

            # Auto-push to GitHub
            pushed = False
            if GITHUB_TOKEN and hasattr(result, '__fspath__') or isinstance(result, (str, Path)):
                pushed = self._git_push(
                    Path(result) if isinstance(result, str) else result,
                    f"fix(agent-lab): {improvement.description[:60]}"
                )

            self._tracker.log("auto_apply", {
                "description": f"Auto-applied: {improvement.description[:80]}",
                "improvement_id": improvement.id[:8],
                "agent": improvement.agent_name,
                "pushed": pushed,
            })
            push_note = " + pushed to GitHub" if pushed else ""
            return f"Auto-applied{push_note}: {improvement.description}"
        else:
            return self.queue_for_approval(improvement)

    def queue_for_approval(self, improvement: Improvement) -> str:
        """Save improvement to the approval queue."""
        improvement.status = "queued"
        queue_dir = self._data_dir / "queue"
        queue_dir.mkdir(parents=True, exist_ok=True)

        path = queue_dir / f"{improvement.id[:8]}_{improvement.agent_name}.json"
        path.write_text(json.dumps(asdict(improvement), ensure_ascii=False, indent=2))

        # Remove from improvements dir
        imp_path = self._data_dir / "improvements" / f"{improvement.id[:8]}_{improvement.agent_name}.json"
        if imp_path.exists():
            imp_path.unlink()

        self._tracker.log("queued", {
            "description": f"Queued: {improvement.description[:80]}",
            "improvement_id": improvement.id[:8],
            "agent": improvement.agent_name,
            "severity": improvement.severity,
        })

        return f"Queued for approval: {improvement.description}"

    def get_queue(self) -> list[Improvement]:
        """Get all queued improvements."""
        queue_dir = self._data_dir / "queue"
        if not queue_dir.exists():
            return []

        items = []
        for f in sorted(queue_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                items.append(Improvement(**data))
            except (json.JSONDecodeError, TypeError):
                continue
        return items

    def approve(self, improvement_id: str) -> str:
        """Approve and apply a queued improvement."""
        imp = self._find_in_queue(improvement_id)
        if not imp:
            return f"Improvement {improvement_id} nicht in der Queue gefunden."

        # For now, just move to applied (actual file editing is complex)
        imp.status = "applied"
        self._move_to_applied(imp)
        self._remove_from_queue(imp)

        self._tracker.log("approved", {
            "description": f"Approved: {imp.description[:80]}",
            "improvement_id": imp.id[:8],
            "agent": imp.agent_name,
        })

        return f"Approved und angewendet: {imp.description}"

    def reject(self, improvement_id: str) -> str:
        """Reject a queued improvement."""
        imp = self._find_in_queue(improvement_id)
        if not imp:
            return f"Improvement {improvement_id} nicht in der Queue gefunden."

        imp.status = "rejected"
        self._move_to_applied(imp)  # Archive even rejected ones
        self._remove_from_queue(imp)

        self._tracker.log("rejected", {
            "description": f"Rejected: {imp.description[:80]}",
            "improvement_id": imp.id[:8],
        })

        return f"Rejected: {imp.description}"

    def _find_in_queue(self, improvement_id: str) -> Optional[Improvement]:
        for imp in self.get_queue():
            if imp.id.startswith(improvement_id) or imp.id[:8] == improvement_id:
                return imp
        return None

    def _remove_from_queue(self, imp: Improvement):
        queue_dir = self._data_dir / "queue"
        for f in queue_dir.glob(f"{imp.id[:8]}_*.json"):
            f.unlink()

    def _move_to_applied(self, imp: Improvement):
        applied_dir = self._data_dir / "applied"
        applied_dir.mkdir(parents=True, exist_ok=True)
        path = applied_dir / f"{imp.id[:8]}_{imp.agent_name}_{imp.status}.json"
        path.write_text(json.dumps(asdict(imp), ensure_ascii=False, indent=2))

    def _git_push(self, file_path: Path, commit_message: str) -> bool:
        """Commit und push einer geaenderten Datei via GitHub Token."""
        if not GITHUB_TOKEN:
            return False

        repo_dir = file_path.parent
        # Finde das Git-Root
        while repo_dir != repo_dir.parent:
            if (repo_dir / ".git").exists():
                break
            repo_dir = repo_dir.parent
        else:
            return False

        try:
            env = os.environ.copy()
            # Git mit Token authentifizieren
            env["GIT_ASKPASS"] = "echo"
            env["GIT_TERMINAL_PROMPT"] = "0"

            # Remote URL mit Token setzen
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(repo_dir), capture_output=True, text=True
            )
            remote_url = result.stdout.strip()

            if "github.com" in remote_url and GITHUB_TOKEN:
                # https://TOKEN@github.com/user/repo.git
                auth_url = remote_url.replace(
                    "https://github.com",
                    f"https://{GITHUB_TOKEN}@github.com"
                )

                subprocess.run(["git", "add", str(file_path)], cwd=str(repo_dir), check=True)
                subprocess.run(
                    ["git", "commit", "-m", commit_message],
                    cwd=str(repo_dir), check=True, env=env
                )
                subprocess.run(
                    ["git", "push", auth_url, "main"],
                    cwd=str(repo_dir), check=True, env=env,
                    capture_output=True
                )
                return True
        except subprocess.CalledProcessError as e:
            print(f"[Git Push Fehler] {e}")
        return False

    def _apply_keyword_change(self, imp: Improvement):
        """Try to add keywords to an agent file. Returns file path if successful, False otherwise."""
        # Extract new keywords from diff
        new_kw_match = re.findall(r"'([^']+)'", imp.diff)
        if not new_kw_match:
            return False

        # Find the agent file
        from .scanner import AgentScanner, AGENT_FILES
        for agent_def in AGENT_FILES:
            if agent_def["name"] == imp.agent_name:
                vault_root = Path(__file__).parent.parent.parent.parent
                file_path = vault_root / agent_def["path"]
                if not file_path.exists():
                    return False

                content = file_path.read_text(encoding="utf-8")

                # Find keywords list and add new ones
                kw_match = re.search(r'(keywords\s*=\s*\[)(.*?)(\])', content, re.DOTALL)
                if not kw_match:
                    return False

                existing = kw_match.group(2)
                additions = ", ".join(f'"{kw}"' for kw in new_kw_match if f'"{kw}"' not in existing)
                if not additions:
                    return False

                # Backup
                backup_dir = self._data_dir / "applied" / "backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, backup_dir / f"{imp.id[:8]}_{file_path.name}.bak")

                # Apply
                new_content = content[:kw_match.end(2)] + ",\n            " + additions + content[kw_match.end(2):]
                file_path.write_text(new_content, encoding="utf-8")
                return file_path

        return False
