"""Handler for message tool."""

from __future__ import annotations

from typing import Any

from opendev.core.context_engineering.tools.implementations.message_tool import MessageTool


class MessageToolHandler:
    """Handles send_message tool invocations."""

    def __init__(self) -> None:
        self._tool = MessageTool()

    def handle(self, arguments: dict[str, Any], context: Any = None) -> dict[str, Any]:
        return self._tool.execute(
            channel=arguments.get("channel", ""),
            target=arguments.get("target"),
            message=arguments.get("message", ""),
            format=arguments.get("format", "text"),
        )
