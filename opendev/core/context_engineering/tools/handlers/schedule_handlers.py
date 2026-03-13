"""Handler for schedule tool."""

from __future__ import annotations

from typing import Any

from opendev.core.context_engineering.tools.implementations.schedule_tool import ScheduleTool


class ScheduleToolHandler:
    """Handles schedule tool invocations."""

    def __init__(self) -> None:
        self._tool = ScheduleTool()

    def handle(self, arguments: dict[str, Any], context: Any = None) -> dict[str, Any]:
        action = arguments.get("action", "")
        params = {k: v for k, v in arguments.items() if k != "action"}
        return self._tool.execute(action, **params)
