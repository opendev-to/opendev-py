"""Schedule tool — manage recurring tasks via cron-like expressions."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEDULES_FILE = Path.home() / ".opendev" / "schedules.json"


def _load_schedules() -> list[dict[str, Any]]:
    """Load schedules from disk."""
    if not _SCHEDULES_FILE.exists():
        return []
    try:
        with open(_SCHEDULES_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_schedules(schedules: list[dict[str, Any]]) -> None:
    """Save schedules to disk."""
    _SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_SCHEDULES_FILE, "w") as f:
        json.dump(schedules, f, indent=2, default=str)


class ScheduleTool:
    """Manage scheduled tasks (persisted to ~/.opendev/schedules.json)."""

    def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        """Dispatch to schedule action."""
        actions = {
            "list": self._list,
            "add": self._add,
            "remove": self._remove,
            "run_now": self._run_now,
            "status": self._status,
        }
        handler = actions.get(action)
        if not handler:
            return {
                "success": False,
                "error": f"Unknown schedule action: {action}. Available: {', '.join(actions.keys())}",
                "output": None,
            }
        return handler(**kwargs)

    def _list(self, **kwargs: Any) -> dict[str, Any]:
        schedules = _load_schedules()
        if not schedules:
            return {"success": True, "output": "No scheduled tasks.", "schedules": []}

        parts = [f"Scheduled tasks ({len(schedules)}):\n"]
        for s in schedules:
            status = "enabled" if s.get("enabled", True) else "disabled"
            parts.append(f"  [{s['name']}] {s['cron']} — {s['command']} ({status})")
            if s.get("last_run"):
                parts.append(f"    Last run: {s['last_run']}")

        return {"success": True, "output": "\n".join(parts), "schedules": schedules}

    def _add(
        self, name: str = "", cron: str = "", command: str = "", **kwargs: Any
    ) -> dict[str, Any]:
        if not name:
            return {"success": False, "error": "name is required", "output": None}
        if not cron:
            return {"success": False, "error": "cron expression is required", "output": None}
        if not command:
            return {"success": False, "error": "command is required", "output": None}

        schedules = _load_schedules()

        # Check for duplicate name
        if any(s["name"] == name for s in schedules):
            return {
                "success": False,
                "error": f"Schedule '{name}' already exists. Remove it first or use a different name.",
                "output": None,
            }

        schedule = {
            "name": name,
            "cron": cron,
            "command": command,
            "enabled": True,
            "created_at": datetime.now().isoformat(),
            "last_run": None,
        }
        schedules.append(schedule)
        _save_schedules(schedules)

        return {
            "success": True,
            "output": f"Added schedule '{name}': {cron} — {command}",
        }

    def _remove(self, name: str = "", **kwargs: Any) -> dict[str, Any]:
        if not name:
            return {"success": False, "error": "name is required", "output": None}

        schedules = _load_schedules()
        new_schedules = [s for s in schedules if s["name"] != name]

        if len(new_schedules) == len(schedules):
            return {"success": False, "error": f"Schedule '{name}' not found", "output": None}

        _save_schedules(new_schedules)
        return {"success": True, "output": f"Removed schedule '{name}'"}

    def _run_now(self, name: str = "", **kwargs: Any) -> dict[str, Any]:
        """Trigger immediate execution of a scheduled task."""
        if not name:
            return {"success": False, "error": "name is required", "output": None}

        schedules = _load_schedules()
        schedule = next((s for s in schedules if s["name"] == name), None)
        if not schedule:
            return {"success": False, "error": f"Schedule '{name}' not found", "output": None}

        import subprocess

        try:
            result = subprocess.run(
                schedule["command"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            # Update last_run
            schedule["last_run"] = datetime.now().isoformat()
            _save_schedules(schedules)

            output = result.stdout.strip()
            if result.returncode != 0:
                error = result.stderr.strip()
                return {
                    "success": False,
                    "error": f"Command failed (exit {result.returncode}): {error}",
                    "output": output,
                }
            return {"success": True, "output": output or "Command completed successfully"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out after 60s", "output": None}

    def _status(self, **kwargs: Any) -> dict[str, Any]:
        schedules = _load_schedules()
        enabled = sum(1 for s in schedules if s.get("enabled", True))
        return {
            "success": True,
            "output": f"Scheduler: {len(schedules)} tasks ({enabled} enabled)",
            "total": len(schedules),
            "enabled": enabled,
        }
