"""Handler for memory tools."""

from __future__ import annotations

from typing import Any

from opendev.core.context_engineering.tools.implementations.memory_tools import MemoryTools


class MemoryToolHandler:
    """Handles memory_search and memory_write tool invocations."""

    def __init__(self, working_dir: str | None = None) -> None:
        self._tools = MemoryTools(working_dir=working_dir)

    def set_working_dir(self, working_dir: str) -> None:
        """Update the working directory."""
        self._tools = MemoryTools(working_dir=working_dir)

    def search(self, arguments: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """Execute memory_search tool."""
        return self._tools.search(
            query=arguments.get("query", ""),
            max_results=arguments.get("max_results", 5),
        )

    def write(self, arguments: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """Execute memory_write tool."""
        return self._tools.write(
            topic=arguments.get("topic", ""),
            content=arguments.get("content", ""),
            file=arguments.get("file"),
            scope=arguments.get("scope", "project"),
        )
