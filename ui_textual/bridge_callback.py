"""Bridge callback that forwards agent events to both TUI and WebSocket."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from opendev.ui_textual.callback_interface import BaseUICallback
from opendev.models.message import ToolCall

logger = logging.getLogger(__name__)


class BridgeUICallback(BaseUICallback):
    """Forwards every UI callback event to the TUI callback (primary) and
    an optional WebUICallback (secondary, fire-and-forget).

    The TUI callback is always called first and its errors propagate normally.
    The web callback is wrapped in try/except so web failures never affect the TUI.
    """

    def __init__(self, tui_callback: Any, web_callback: Any = None) -> None:
        self._tui = tui_callback
        self._web = web_callback

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _forward_web(self, method_name: str, *args: Any, **kwargs: Any) -> None:
        """Call method on web callback, swallowing any errors."""
        if self._web is None:
            return
        fn = getattr(self._web, method_name, None)
        if fn is None:
            return
        try:
            fn(*args, **kwargs)
        except Exception as exc:
            logger.warning("BridgeUICallback: web.%s failed: %s", method_name, exc)

    # ------------------------------------------------------------------
    # Thinking lifecycle
    # ------------------------------------------------------------------

    def on_thinking_start(self) -> None:
        self._tui.on_thinking_start()
        self._forward_web("on_thinking_start")

    def on_thinking_complete(self) -> None:
        self._tui.on_thinking_complete()
        self._forward_web("on_thinking_complete")

    def on_thinking(self, content: str) -> None:
        if hasattr(self._tui, "on_thinking"):
            self._tui.on_thinking(content)
        self._forward_web("on_thinking", content)

    def on_critique(self, content: str) -> None:
        if hasattr(self._tui, "on_critique"):
            self._tui.on_critique(content)
        self._forward_web("on_critique", content)

    # ------------------------------------------------------------------
    # Assistant message
    # ------------------------------------------------------------------

    def on_assistant_message(self, content: str) -> None:
        self._tui.on_assistant_message(content)
        self._forward_web("on_assistant_message", content)

    def on_message(self, message: str) -> None:
        self._tui.on_message(message)
        self._forward_web("on_message", message)

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def on_progress_start(self, message: str) -> None:
        self._tui.on_progress_start(message)
        self._forward_web("on_progress_start", message)

    def on_progress_update(self, message: str) -> None:
        self._tui.on_progress_update(message)
        self._forward_web("on_progress_update", message)

    def on_progress_complete(self, message: str = "", success: bool = True) -> None:
        self._tui.on_progress_complete(message, success=success)
        self._forward_web("on_progress_complete", message, success=success)

    # ------------------------------------------------------------------
    # Interrupt
    # ------------------------------------------------------------------

    def on_interrupt(self, context: Any = None) -> None:
        if hasattr(self._tui, "on_interrupt"):
            try:
                self._tui.on_interrupt(context)
            except TypeError:
                self._tui.on_interrupt()
        self._forward_web("on_interrupt", context)

    def mark_interrupt_shown(self) -> None:
        if hasattr(self._tui, "mark_interrupt_shown"):
            self._tui.mark_interrupt_shown()
        self._forward_web("mark_interrupt_shown")

    # ------------------------------------------------------------------
    # Tool lifecycle
    # ------------------------------------------------------------------

    def on_tool_call(
        self, tool_name: str, tool_args: Dict[str, Any], tool_call_id: str = ""
    ) -> None:
        if hasattr(self._tui, "on_tool_call"):
            try:
                self._tui.on_tool_call(tool_name, tool_args, tool_call_id=tool_call_id)
            except TypeError:
                self._tui.on_tool_call(tool_name, tool_args)
        self._forward_web("on_tool_call", tool_name, tool_args, tool_call_id=tool_call_id)

    def on_tool_result(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: Any,
        tool_call_id: str = "",
    ) -> None:
        if hasattr(self._tui, "on_tool_result"):
            try:
                self._tui.on_tool_result(tool_name, tool_args, result, tool_call_id=tool_call_id)
            except TypeError:
                self._tui.on_tool_result(tool_name, tool_args, result)
        self._forward_web("on_tool_result", tool_name, tool_args, result, tool_call_id=tool_call_id)

    def on_tool_complete(
        self,
        tool_name: str,
        success: bool,
        message: str,
        details: Optional[str] = None,
    ) -> None:
        if hasattr(self._tui, "on_tool_complete"):
            self._tui.on_tool_complete(tool_name, success, message, details=details)
        self._forward_web("on_tool_complete", tool_name, success, message, details=details)

    def on_bash_output_line(self, line: str, is_stderr: bool = False) -> None:
        if hasattr(self._tui, "on_bash_output_line"):
            self._tui.on_bash_output_line(line, is_stderr=is_stderr)
        self._forward_web("on_bash_output_line", line, is_stderr=is_stderr)

    # ------------------------------------------------------------------
    # Nested tool calls (subagent)
    # ------------------------------------------------------------------

    def on_nested_tool_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        depth: int = 1,
        parent: str = "",
    ) -> None:
        if hasattr(self._tui, "on_nested_tool_call"):
            self._tui.on_nested_tool_call(tool_name, tool_args, depth=depth, parent=parent)
        self._forward_web("on_nested_tool_call", tool_name, tool_args, depth=depth, parent=parent)

    def on_nested_tool_result(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: Any,
        depth: int = 1,
        parent: str = "",
    ) -> None:
        if hasattr(self._tui, "on_nested_tool_result"):
            self._tui.on_nested_tool_result(
                tool_name, tool_args, result, depth=depth, parent=parent
            )
        self._forward_web(
            "on_nested_tool_result", tool_name, tool_args, result, depth=depth, parent=parent
        )

    # ------------------------------------------------------------------
    # Subagent lifecycle
    # ------------------------------------------------------------------

    def on_single_agent_start(self, agent_type: str, description: str, tool_call_id: str) -> None:
        self._tui.on_single_agent_start(agent_type, description, tool_call_id)
        self._forward_web("on_single_agent_start", agent_type, description, tool_call_id)

    def on_single_agent_complete(
        self, tool_call_id: str, success: bool, failure_reason: str = ""
    ) -> None:
        self._tui.on_single_agent_complete(tool_call_id, success, failure_reason=failure_reason)
        self._forward_web(
            "on_single_agent_complete",
            tool_call_id,
            success,
            failure_reason=failure_reason,
        )

    def on_parallel_agents_start(self, agent_infos: list) -> None:
        self._tui.on_parallel_agents_start(agent_infos)
        self._forward_web("on_parallel_agents_start", agent_infos)

    def on_parallel_agent_complete(self, tool_call_id: str, success: bool) -> None:
        self._tui.on_parallel_agent_complete(tool_call_id, success)
        self._forward_web("on_parallel_agent_complete", tool_call_id, success)

    def on_parallel_agents_done(self) -> None:
        self._tui.on_parallel_agents_done()
        self._forward_web("on_parallel_agents_done")

    # ------------------------------------------------------------------
    # Cost / context tracking
    # ------------------------------------------------------------------

    def on_cost_update(self, total_cost_usd: float) -> None:
        self._tui.on_cost_update(total_cost_usd)
        self._forward_web("on_cost_update", total_cost_usd)

    def on_context_usage(self, usage_pct: float) -> None:
        self._tui.on_context_usage(usage_pct)
        self._forward_web("on_context_usage", usage_pct)

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------

    def on_debug(self, message: str, prefix: str = "DEBUG") -> None:
        if hasattr(self._tui, "on_debug"):
            self._tui.on_debug(message, prefix=prefix)
        self._forward_web("on_debug", message, prefix=prefix)

    # ------------------------------------------------------------------
    # Plan approval (delegate to TUI — Web UI shows read-only indicator)
    # ------------------------------------------------------------------

    def set_plan_approval_callback(self, callback: Any) -> None:
        if hasattr(self._tui, "set_plan_approval_callback"):
            self._tui.set_plan_approval_callback(callback)

    def display_plan_content(self, plan_content: str) -> None:
        if hasattr(self._tui, "display_plan_content"):
            self._tui.display_plan_content(plan_content)
        self._forward_web("display_plan_content", plan_content)

    def request_plan_approval(
        self, plan_content: str = "", allowed_prompts: Any = None
    ) -> Dict[str, str]:
        if hasattr(self._tui, "request_plan_approval"):
            return self._tui.request_plan_approval(plan_content, allowed_prompts)
        return {"action": "reject", "feedback": ""}

    # ------------------------------------------------------------------
    # Nested calls collector (session persistence)
    # ------------------------------------------------------------------

    def get_and_clear_nested_calls(self) -> list:
        tui_calls = []
        if hasattr(self._tui, "get_and_clear_nested_calls"):
            tui_calls = self._tui.get_and_clear_nested_calls()
        # Also drain web callback's collector
        if self._web and hasattr(self._web, "get_and_clear_nested_calls"):
            try:
                self._web.get_and_clear_nested_calls()
            except Exception:
                pass
        return tui_calls
