"""Handler for session inspection tools."""

from __future__ import annotations

from typing import Any, Union

from opendev.core.context_engineering.tools.implementations.session_tools import SessionTools


class SessionToolHandler:
    """Handles list_sessions, get_session_history, and list_subagents."""

    def __init__(self) -> None:
        self._tools = SessionTools()
        self._subagent_manager: Union[Any, None] = None

    def set_subagent_manager(self, manager: Any) -> None:
        """Set the subagent manager reference."""
        self._subagent_manager = manager

    def list_sessions(self, arguments: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """Execute list_sessions tool."""
        session_manager = getattr(context, "session_manager", None) if context else None
        return self._tools.list_sessions(
            session_manager=session_manager,
            limit=arguments.get("limit", 20),
        )

    def get_session_history(
        self, arguments: dict[str, Any], context: Any = None
    ) -> dict[str, Any]:
        """Execute get_session_history tool."""
        session_manager = getattr(context, "session_manager", None) if context else None
        return self._tools.get_session_history(
            session_manager=session_manager,
            session_id=arguments.get("session_id", ""),
            limit=arguments.get("limit", 50),
            include_tool_calls=arguments.get("include_tool_calls", False),
        )

    def list_subagents(self, arguments: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """Execute list_subagents tool."""
        return self._tools.list_subagents(subagent_manager=self._subagent_manager)
