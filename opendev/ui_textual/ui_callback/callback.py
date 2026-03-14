"""UI callback for real-time tool call display in Textual UI."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from opendev.ui_textual.formatters.style_formatter import StyleFormatter
from opendev.ui_textual.style_tokens import GREY, PRIMARY
from opendev.ui_textual.services import ToolDisplayService
from opendev.models.message import ToolCall
from opendev.ui_textual.ui_callback.tool_display import CallbackToolDisplayMixin
from opendev.ui_textual.ui_callback.agent_display import CallbackAgentDisplayMixin
from opendev.ui_textual.ui_callback.plan_approval import CallbackPlanApprovalMixin

logger = logging.getLogger(__name__)


class TextualUICallback(
    CallbackToolDisplayMixin,
    CallbackAgentDisplayMixin,
    CallbackPlanApprovalMixin,
):
    """Callback for real-time display of agent actions in Textual UI."""

    def __init__(self, conversation_log, chat_app=None, working_dir: Optional[Path] = None):
        """Initialize the UI callback.

        Args:
            conversation_log: The ConversationLog widget to display messages
            chat_app: The main chat app (OpenDevChatApp instance) for controlling processing state
            working_dir: Working directory for resolving relative paths in tool displays
        """
        self.conversation = conversation_log
        self.chat_app = chat_app
        # chat_app IS the Textual App instance itself, not a wrapper
        self._app = chat_app
        self.formatter = StyleFormatter()
        self._current_thinking = False
        # Spinner IDs for tracking active spinners via SpinnerService
        self._progress_spinner_id: str = ""
        # Dict to track multiple tool spinners for parallel execution
        # Maps tool_call_id -> spinner_id
        self._tool_spinner_ids: Dict[str, str] = {}
        # Working directory for resolving relative paths
        self._working_dir = working_dir
        # Unified display service for formatting (single source of truth)
        self._display_service = ToolDisplayService(working_dir)
        # Collector for nested tool calls (for session storage)
        self._pending_nested_calls: list[ToolCall] = []
        # Thinking mode visibility toggle (default OFF)
        self._thinking_visible = False
        # Track parallel agent group state SYNCHRONOUSLY to avoid race conditions
        # This is set immediately when parallel agents start, before async UI update
        self._in_parallel_agent_group: bool = False
        # Track current single agent ID for completion callback
        self._current_single_agent_id: str | None = None
        # Guard against duplicate interrupt messages (Fix 3)
        self._interrupt_shown: bool = False

    def mark_interrupt_shown(self) -> None:
        """Mark that interrupt feedback has been shown (called from phase 1)."""
        self._interrupt_shown = True

    def on_thinking_start(self) -> None:
        """Called when the agent starts thinking."""
        self._current_thinking = True
        self._interrupt_shown = False  # Reset guard for new run (Fix 3)
        # Reset chat_app flag so next interrupt can show a message
        if self.chat_app:
            self.chat_app._interrupt_message_written = False
        # Reset tool_renderer interrupt flag for new run
        if hasattr(self.conversation, "reset_interrupt"):
            self._run_on_ui(self.conversation.reset_interrupt)

        # The app's built-in spinner should already be running with our custom message
        # We don't need to start another spinner, just note that thinking has started

    def on_thinking_complete(self) -> None:
        """Called when the agent completes thinking."""
        if self._current_thinking:
            # Don't stop the spinner here - let it continue during tool execution
            # The app will stop it when the entire process is complete
            self._current_thinking = False

    def on_thinking(self, content: str) -> None:
        """Called when the model produces thinking content via the think tool.

        Displays thinking content in the conversation log with dark gray styling.
        Can be toggled on/off with Ctrl+Shift+T hotkey.

        Args:
            content: The reasoning/thinking text from the model
        """
        # Check visibility from chat_app (single source of truth) or fallback to local state
        if self.chat_app and hasattr(self.chat_app, "_thinking_visible"):
            if not self.chat_app._thinking_visible:
                return  # Skip display if thinking is hidden
        elif not self._thinking_visible:
            return  # Fallback to local state

        if not content or not content.strip():
            return

        # Stop spinner BEFORE displaying thinking trace (so it appears above, not below)
        if self.chat_app and hasattr(self.chat_app, "_stop_local_spinner"):
            self._run_on_ui(self.chat_app._stop_local_spinner)

        # Display thinking block with special styling
        if hasattr(self.conversation, "add_thinking_block"):
            self._run_on_ui(self.conversation.add_thinking_block, content)

        # Restart spinner for the action phase — but NOT if interrupted
        should_restart = True
        if self.chat_app and hasattr(self.chat_app, "_interrupt_manager"):
            token = self.chat_app._interrupt_manager._active_interrupt_token
            if token and token.is_requested():
                should_restart = False
        if should_restart and self.chat_app and hasattr(self.chat_app, "_start_local_spinner"):
            self._run_on_ui(self.chat_app._start_local_spinner)

    def toggle_thinking_visibility(self) -> bool:
        """Toggle thinking content visibility.

        Syncs with chat_app state if available.

        Returns:
            New visibility state (True = visible)
        """
        # Toggle app state (single source of truth) if available
        if self.chat_app and hasattr(self.chat_app, "_thinking_visible"):
            self.chat_app._thinking_visible = not self.chat_app._thinking_visible
            self._thinking_visible = self.chat_app._thinking_visible
            return self.chat_app._thinking_visible
        else:
            # Fallback to local state
            self._thinking_visible = not self._thinking_visible
            return self._thinking_visible

    def on_critique(self, content: str) -> None:
        """Called when the model produces critique content for a thinking trace.

        Displays critique content in the conversation log with special styling.
        Only shown when thinking level is High.

        Args:
            content: The critique/feedback text from the critique phase
        """
        # Check if thinking is visible (critique only shows when thinking is visible)
        if self.chat_app and hasattr(self.chat_app, "_thinking_visible"):
            if not self.chat_app._thinking_visible:
                return  # Skip display if thinking is hidden
        elif not self._thinking_visible:
            return  # Fallback to local state

        if not content or not content.strip():
            return

        # Stop spinner BEFORE displaying critique trace (so it appears above, not below)
        if self.chat_app and hasattr(self.chat_app, "_stop_local_spinner"):
            self._run_on_ui(self.chat_app._stop_local_spinner)

        # Display critique block with special styling (reuse thinking block with prefix)
        if hasattr(self.conversation, "add_thinking_block"):
            self._run_on_ui(self.conversation.add_thinking_block, content)

        # Restart spinner for the next phase — but NOT if interrupted
        should_restart = True
        if self.chat_app and hasattr(self.chat_app, "_interrupt_manager"):
            token = self.chat_app._interrupt_manager._active_interrupt_token
            if token and token.is_requested():
                should_restart = False
        if should_restart and self.chat_app and hasattr(self.chat_app, "_start_local_spinner"):
            self._run_on_ui(self.chat_app._start_local_spinner)

    def get_and_clear_nested_calls(self) -> list[ToolCall]:
        """Return collected nested calls and clear the buffer.

        Called after spawn_subagent completes to attach nested calls to the ToolCall.
        """
        calls = self._pending_nested_calls
        self._pending_nested_calls = []
        return calls

    def on_assistant_message(self, content: str) -> None:
        """Called when assistant provides a message before tool execution.

        Args:
            content: The assistant's message/thinking
        """
        if content and content.strip():
            # Stop spinner before showing assistant message
            # Note: Only call _stop_local_spinner which goes through SpinnerController
            # with grace period. Don't call conversation.stop_spinner directly as it
            # bypasses the grace period and removes the spinner immediately.
            if self.chat_app and hasattr(self.chat_app, "_stop_local_spinner"):
                self._run_on_ui(self.chat_app._stop_local_spinner)

            # Display the assistant's thinking/message (via ledger if available)
            ledger = getattr(self._app, "_display_ledger", None) if self._app else None
            if ledger:
                ledger.display_assistant_message(content, "ui_callback", call_on_ui=self._run_on_ui)
            elif hasattr(self.conversation, "add_assistant_message"):
                logger.warning(
                    "DisplayLedger not available, falling back to direct display " "(source=%s)",
                    "ui_callback",
                )
                self._run_on_ui(self.conversation.add_assistant_message, content)
            # Force refresh to ensure immediate visual update
            if hasattr(self.conversation, "refresh"):
                self._run_on_ui(self.conversation.refresh)

    def on_message(self, message: str) -> None:
        """Called to display a simple progress message (no spinner).

        Args:
            message: The message to display
        """
        if hasattr(self.conversation, "add_system_message"):
            self._run_on_ui(self.conversation.add_system_message, message)

    def on_progress_start(self, message: str) -> None:
        """Called when a progress operation starts (shows spinner).

        Args:
            message: The progress message to display with spinner
        """
        # Use SpinnerService for unified spinner management
        if self._app is not None and hasattr(self._app, "spinner_service"):
            self._progress_spinner_id = self._app.spinner_service.start(message)
        else:
            # Fallback to direct calls if SpinnerService not available
            from rich.text import Text

            display_text = Text(message, style=PRIMARY)
            if hasattr(self.conversation, "add_tool_call") and self._app is not None:
                self._app.call_from_thread(self.conversation.add_tool_call, display_text)
            if hasattr(self.conversation, "start_tool_execution") and self._app is not None:
                self._app.call_from_thread(self.conversation.start_tool_execution)

    def on_progress_update(self, message: str) -> None:
        """Update progress text in-place (same line, keeps spinner running).

        Use this for multi-step progress where you want to update the text
        without creating a new line. The spinner and timer continue running.

        Args:
            message: New progress message to display
        """
        # Use SpinnerService for unified spinner management
        if (
            self._progress_spinner_id
            and self._app is not None
            and hasattr(self._app, "spinner_service")
        ):
            self._app.spinner_service.update(self._progress_spinner_id, message)
        else:
            # Fallback to direct calls if SpinnerService not available
            from rich.text import Text

            display_text = Text(message, style=PRIMARY)
            if hasattr(self.conversation, "update_progress_text"):
                self._run_on_ui(self.conversation.update_progress_text, display_text)

    def on_progress_complete(self, message: str = "", success: bool = True) -> None:
        """Called when a progress operation completes.

        Args:
            message: Optional result message to display
            success: Whether the operation succeeded (affects bullet color)
        """
        # Use SpinnerService for unified spinner management
        if (
            self._progress_spinner_id
            and self._app is not None
            and hasattr(self._app, "spinner_service")
        ):
            self._app.spinner_service.stop(self._progress_spinner_id, success, message)
            self._progress_spinner_id = ""
        else:
            # Fallback to direct calls if SpinnerService not available
            from rich.text import Text

            # Stop spinner (shows green/red bullet based on success)
            if hasattr(self.conversation, "stop_tool_execution"):
                self._run_on_ui(lambda: self.conversation.stop_tool_execution(success))

            # Show result line (if message provided)
            if message:
                result_line = Text("  ⎿  ", style=GREY)
                result_line.append(message, style=GREY)
                self._run_on_ui(self.conversation.write, result_line)

    def on_interrupt(self, context: str = "thinking") -> None:
        """Called when execution is interrupted by user.

        Displays the interrupt message based on context:
        - "thinking": Show below/replacing blank line after user prompt
        - "tool": Show below the tool name being executed

        Args:
            context: "thinking" for prompt phase, "tool" for tool execution
        """
        # Guard against duplicate interrupt messages (Fix 3)
        if self._interrupt_shown:
            return
        self._interrupt_shown = True

        # Guard: if UI thread already wrote the interrupt message, just clean up spinners
        if self.chat_app and getattr(self.chat_app, "_interrupt_message_written", False):
            self._cleanup_spinners()
            return

        try:
            self._cleanup_spinners()
            self._show_interrupt_message(context)
        except Exception as e:
            # Fallback: at minimum ensure processing state is cleared
            logger.error(f"Interrupt handler error: {e}")
            if self.chat_app:
                self.chat_app._is_processing = False

    def _cleanup_spinners(self) -> None:
        """Stop all active spinners during interrupt."""
        # Stop any active spinners via SpinnerService
        if self._app is not None and hasattr(self._app, "spinner_service"):
            # Stop all tracked tool spinners (explicitly pass empty result message)
            for spinner_id in list(self._tool_spinner_ids.values()):
                self._app.spinner_service.stop(spinner_id, success=False, result_message="")
            self._tool_spinner_ids.clear()

            if self._progress_spinner_id:
                self._app.spinner_service.stop(
                    self._progress_spinner_id, success=False, result_message=""
                )
                self._progress_spinner_id = ""

        # Stop spinner first - this removes spinner lines but leaves the blank line after user prompt
        if hasattr(self.conversation, "stop_spinner"):
            self._run_on_ui(self.conversation.stop_spinner)
        if self.chat_app and hasattr(self.chat_app, "_stop_local_spinner"):
            self._run_on_ui(self.chat_app._stop_local_spinner)

    def _show_interrupt_message(self, context: str) -> None:
        """Display the interrupt message based on context.

        Args:
            context: "thinking" or "tool"
        """

        def write_interrupt():
            from opendev.ui_textual.utils.interrupt_utils import (
                strip_trailing_blanks,
                create_interrupt_text,
                STANDARD_INTERRUPT_MESSAGE,
            )

            # Mark on chat_app so UI thread's _show_interrupt_feedback() won't duplicate
            if self.chat_app:
                self.chat_app._interrupt_message_written = True
            strip_trailing_blanks(self.conversation)
            self.conversation.write(create_interrupt_text(STANDARD_INTERRUPT_MESSAGE))

        self._run_on_ui(write_interrupt)

    def on_bash_output_line(self, line: str, is_stderr: bool = False) -> None:
        """Called for each line of bash output during execution.

        For main agent: Output is collected and shown via add_bash_output_box in on_tool_result.
        For subagents: ForwardingUICallback forwards this to parent for nested display.

        Args:
            line: A single line of output from the bash command
            is_stderr: True if this line came from stderr
        """
        # Main agent doesn't stream - output shown in on_tool_result
        pass

    def _normalize_arguments(self, tool_args: Any) -> Dict[str, Any]:
        """Ensure tool arguments are represented as a dictionary and normalize URLs for display.

        Delegates to ToolDisplayService for unified logic.
        """
        return self._display_service.normalize_arguments(tool_args)

    def _resolve_paths_in_args(self, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve relative paths to absolute paths for display.

        Delegates to ToolDisplayService for unified logic.

        Args:
            tool_args: Tool arguments dict

        Returns:
            Copy of tool_args with paths resolved to absolute paths
        """
        return self._display_service.resolve_paths(tool_args)

    def _run_on_ui(self, func, *args, **kwargs) -> None:
        """Execute a function on the Textual UI thread and WAIT for completion.

        Uses call_from_thread to ensure ordered execution of UI updates.
        This prevents race conditions where messages are displayed out of order.
        """
        if self._app is not None:
            self._app.call_from_thread(func, *args, **kwargs)
        else:
            func(*args, **kwargs)

    def _run_on_ui_non_blocking(self, func, *args, **kwargs) -> None:
        """Execute a function on the Textual UI thread WITHOUT waiting."""
        if self._app is not None:
            self._app.call_from_thread_nonblocking(func, *args, **kwargs)
        else:
            func(*args, **kwargs)

    def _should_skip_due_to_interrupt(self) -> bool:
        """Check if we should skip UI operations due to interrupt.

        Returns:
            True if an interrupt is pending and we should skip UI updates
        """
        if self.chat_app and hasattr(self.chat_app, "runner"):
            runner = self.chat_app.runner
            if hasattr(runner, "query_processor"):
                query_processor = runner.query_processor
                if hasattr(query_processor, "task_monitor"):
                    task_monitor = query_processor.task_monitor
                    if task_monitor and hasattr(task_monitor, "should_interrupt"):
                        return task_monitor.should_interrupt()
        return False

    def on_debug(self, message: str, prefix: str = "DEBUG") -> None:
        """Called to display debug information about execution flow.

        Args:
            message: The debug message to display
            prefix: Optional prefix for categorizing debug messages
        """
        # Skip debug if interrupted
        if self._should_skip_due_to_interrupt():
            return

        # Display debug message in conversation (non-blocking)
        if hasattr(self.conversation, "add_debug_message"):
            self._run_on_ui_non_blocking(self.conversation.add_debug_message, message, prefix)

    def _refresh_todo_panel(self) -> None:
        """Refresh the todo panel with latest state."""
        if not self.chat_app:
            logger.debug("[CALLBACK] _refresh_todo_panel: no chat_app")
            return

        try:
            from opendev.ui_textual.widgets.todo_panel import TodoPanel

            panel = self.chat_app.query_one("#todo-panel", TodoPanel)
            logger.debug("[CALLBACK] _refresh_todo_panel: calling panel.refresh_display()")
            self._run_on_ui(panel.refresh_display)
        except Exception as e:
            # Panel not found or not initialized yet
            logger.debug(f"[CALLBACK] _refresh_todo_panel: panel not found - {e}")
            pass
