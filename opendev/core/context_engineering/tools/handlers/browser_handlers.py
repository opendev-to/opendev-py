"""Handler for browser automation tool."""

from __future__ import annotations

from typing import Any

from opendev.core.context_engineering.tools.implementations.browser_tool import BrowserTool


class BrowserToolHandler:
    """Handles browser tool invocations."""

    def __init__(self) -> None:
        self._tool = BrowserTool()

    def handle(self, arguments: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """Execute a browser action."""
        return self._tool.execute(
            action=arguments.get("action", ""),
            target=arguments.get("target"),
            value=arguments.get("value"),
            timeout=arguments.get("timeout"),
        )
