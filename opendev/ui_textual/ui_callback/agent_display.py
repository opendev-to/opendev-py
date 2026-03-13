"""Mixin for agent lifecycle display in TextualUICallback."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CallbackAgentDisplayMixin:
    """Mixin handling parallel/single agent lifecycle, context/cost updates, and expansion toggle."""

    # --- Parallel Agent Group Methods ---

    def on_parallel_agents_start(self, agent_infos: list[dict]) -> None:
        """Called when parallel agents start executing.

        Args:
            agent_infos: List of agent info dicts with keys:
                - agent_type: Type of agent (e.g., "Explore")
                - description: Short description of agent's task
                - tool_call_id: Unique ID for tracking this agent
        """
        print(f"[DEBUG] on_parallel_agents_start: {agent_infos}", file=sys.stderr)

        # Stop thinking spinner if still active (shows "Plotting...", etc.)
        if self._current_thinking:
            self._run_on_ui(self.conversation.stop_spinner)
            self._current_thinking = False

        # Stop any local spinner
        if self.chat_app and hasattr(self.chat_app, "_stop_local_spinner"):
            self._run_on_ui(self.chat_app._stop_local_spinner)

        # Set flag SYNCHRONOUSLY before async UI update to prevent race conditions
        # This ensures on_tool_call sees the flag immediately
        self._in_parallel_agent_group = True

        if hasattr(self.conversation, "on_parallel_agents_start") and self._app is not None:
            print("[DEBUG] Calling conversation.on_parallel_agents_start", file=sys.stderr)
            self._app.call_from_thread(
                self.conversation.on_parallel_agents_start,
                agent_infos,
            )
        else:
            print(
                f"[DEBUG] Missing on_parallel_agents_start or app: has_method={hasattr(self.conversation, 'on_parallel_agents_start')}, _app={self._app}",
                file=sys.stderr,
            )

    def on_parallel_agent_complete(self, tool_call_id: str, success: bool) -> None:
        """Called when a parallel agent completes.

        Args:
            tool_call_id: Unique tool call ID of the agent that completed
            success: Whether the agent succeeded
        """
        if self._interrupt_shown:
            return  # interrupt_cleanup already handled display

        if hasattr(self.conversation, "on_parallel_agent_complete") and self._app is not None:
            self._app.call_from_thread(
                self.conversation.on_parallel_agent_complete,
                tool_call_id,
                success,
            )

    def on_context_usage(self, usage_pct: float) -> None:
        """Update context usage display in the status bar."""
        import logging as _log

        _log.getLogger("opendev.context_debug").info(
            "on_context_usage called: pct=%.2f, has_app=%s",
            usage_pct,
            self._app is not None,
        )
        if not self._app:
            return
        try:
            if hasattr(self._app, "status_bar") and self._app.status_bar is not None:
                self._run_on_ui(self._app.status_bar.set_context_usage, usage_pct)
            else:
                from opendev.ui_textual.widgets.status_bar import StatusBar

                sb = self._app.query_one("#status-bar", StatusBar)
                self._run_on_ui(sb.set_context_usage, usage_pct)
        except Exception:
            pass

    def on_cost_update(self, total_cost_usd: float) -> None:
        """Update session cost display in the status bar."""
        if not self._app:
            return
        try:
            if hasattr(self._app, "status_bar") and self._app.status_bar is not None:
                self._run_on_ui(self._app.status_bar.set_session_cost, total_cost_usd)
            else:
                from opendev.ui_textual.widgets.status_bar import StatusBar

                sb = self._app.query_one("#status-bar", StatusBar)
                self._run_on_ui(sb.set_session_cost, total_cost_usd)
        except Exception:
            pass

    def on_parallel_agents_done(self) -> None:
        """Called when all parallel agents have completed."""
        # Clear flag SYNCHRONOUSLY to allow normal tool call display to resume
        self._in_parallel_agent_group = False

        if self._interrupt_shown:
            return  # interrupt_cleanup already handled display

        if hasattr(self.conversation, "on_parallel_agents_done") and self._app is not None:
            self._app.call_from_thread(self.conversation.on_parallel_agents_done)

    def on_single_agent_start(self, agent_type: str, description: str, tool_call_id: str) -> None:
        """Called when a single subagent starts.

        Args:
            agent_type: Type of agent (e.g., "Explore", "Code-Explorer")
            description: Task description
            tool_call_id: Unique ID for tracking
        """
        if hasattr(self.conversation, "on_single_agent_start") and self._app is not None:
            self._app.call_from_thread(
                self.conversation.on_single_agent_start,
                agent_type,
                description,
                tool_call_id,
            )

    def on_single_agent_complete(
        self, tool_call_id: str, success: bool = True, failure_reason: str = ""
    ) -> None:
        """Called when a single subagent completes.

        Args:
            tool_call_id: Unique ID of the agent that completed
            success: Whether the agent succeeded
            failure_reason: Why the agent failed (API error, etc.)
        """
        if self._interrupt_shown:
            return  # interrupt_cleanup already handled display

        if hasattr(self.conversation, "on_single_agent_complete") and self._app is not None:
            self._app.call_from_thread(
                self.conversation.on_single_agent_complete,
                tool_call_id,
                success,
                failure_reason=failure_reason,
            )

    def toggle_parallel_expansion(self) -> bool:
        """Toggle the expand/collapse state of parallel agent display.

        Returns:
            New expansion state (True = expanded)
        """
        if hasattr(self.conversation, "toggle_parallel_expansion"):
            return self.conversation.toggle_parallel_expansion()
        return True

    def has_active_parallel_group(self) -> bool:
        """Check if there's an active parallel agent group.

        Returns:
            True if a parallel group is currently active
        """
        if hasattr(self.conversation, "has_active_parallel_group"):
            return self.conversation.has_active_parallel_group()
        return False
