"""Handler for structured git operations."""

from __future__ import annotations

import os
from typing import Any

from opendev.core.context_engineering.tools.implementations.git_tool import GitTool


class GitToolHandler:
    """Handles git tool invocations."""

    def __init__(self, working_dir: str | None = None) -> None:
        self._working_dir = working_dir or os.getcwd()

    def handle(self, arguments: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """Execute a git action."""
        action = arguments.get("action", "")
        if not action:
            return {"success": False, "error": "action is required", "output": None}

        # Extract non-action params
        params = {k: v for k, v in arguments.items() if k != "action"}

        tool = GitTool(working_dir=self._working_dir)
        return tool.execute(action, **params)
