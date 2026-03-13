"""Frecency-based prompt suggestion manager.

Tracks prompt frequency and recency to provide intelligent autocomplete
suggestions. Score = frequency * (1 / (1 + days_since_last_use)).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FrecencyManager:
    """Tracks and scores prompts by frequency and recency."""

    def __init__(self, history_path: Optional[Path] = None):
        self._history_path = history_path or (
            Path.home() / ".opendev" / "prompt_history.jsonl"
        )
        self._entries: dict[str, dict] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._history_path.exists():
            return
        try:
            for line in self._history_path.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                prompt = entry.get("prompt", "")
                if prompt:
                    self._entries[prompt] = entry
        except Exception:
            logger.debug("Failed to load prompt history", exc_info=True)

    def record(self, prompt: str) -> None:
        """Record a prompt usage."""
        self._ensure_loaded()
        prompt = prompt.strip()
        if not prompt or prompt.startswith("/"):
            return

        now = datetime.now().isoformat()
        if prompt in self._entries:
            self._entries[prompt]["count"] += 1
            self._entries[prompt]["last_used"] = now
        else:
            self._entries[prompt] = {
                "prompt": prompt,
                "count": 1,
                "first_used": now,
                "last_used": now,
            }
        self._save()

    def get_suggestions(self, prefix: str = "", limit: int = 10) -> list[str]:
        """Get top prompts scored by frecency.

        Args:
            prefix: Optional prefix filter.
            limit: Max suggestions to return.

        Returns:
            List of prompts sorted by frecency score (highest first).
        """
        self._ensure_loaded()
        now = datetime.now()
        scored: list[tuple[float, str]] = []

        for prompt, entry in self._entries.items():
            if prefix and not prompt.lower().startswith(prefix.lower()):
                continue
            try:
                last_used = datetime.fromisoformat(entry["last_used"])
                days_since = (now - last_used).total_seconds() / 86400
                score = entry["count"] * (1 / (1 + days_since))
                scored.append((score, prompt))
            except (KeyError, ValueError):
                continue

        scored.sort(reverse=True)
        return [prompt for _, prompt in scored[:limit]]

    def _save(self) -> None:
        """Persist entries to JSONL file."""
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps(entry) for entry in self._entries.values()]
            self._history_path.write_text("\n".join(lines) + "\n")
        except Exception:
            logger.debug("Failed to save prompt history", exc_info=True)
