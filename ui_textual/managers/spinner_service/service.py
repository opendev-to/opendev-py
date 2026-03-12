"""SpinnerService class — centralized spinner management for all UI animations."""

from __future__ import annotations

import threading
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from rich.text import Text

from opendev.ui_textual.style_tokens import GREY, PRIMARY, GREEN_BRIGHT, ERROR
from opendev.ui_textual.managers.spinner_service.models import (
    SpinnerInstance,
    SpinnerType,
    SpinnerFrame,
    SPINNER_CONFIGS,
)
from opendev.ui_textual.managers.spinner_service.animation import AnimationMixin
from opendev.ui_textual.managers.spinner_service.resize import ResizeMixin

if TYPE_CHECKING:
    from textual.app import App
    from textual.timer import Timer
    from opendev.ui_textual.widgets.conversation_log import ConversationLog
    from opendev.ui_textual.components import TipsManager


class SpinnerService(AnimationMixin, ResizeMixin):
    """Centralized spinner management for all UI animations.

    This service provides TWO APIs:

    1. Facade API (for ui_callback compatibility):
       - start(message) -> spinner_id - Start spinner, delegates to ConversationLog
       - update(spinner_id, message) - Update spinner message
       - stop(spinner_id, success, message) - Stop spinner

    2. Callback API (for widgets that manage their own spinners):
       - register(type, callback) -> spinner_id - Register with animation callback
       - update_message(spinner_id, message) - Update message
       - stop(spinner_id, immediate) - Stop spinner

    Thread Safety:
    - All public methods are thread-safe
    - Internal state protected by RLock
    - UI updates dispatched via call_from_thread when needed

    Timer Architecture:
    - Single animation loop with GCD-based tick interval (60ms)
    - Each spinner tracks when its next frame is due
    - Dual-timer pattern: Textual timer (when loop is free) + threading.Timer (fallback)
    """

    def __init__(self, app: "App") -> None:
        """Initialize the SpinnerService.

        Args:
            app: The Textual App instance for timer scheduling
        """
        self.app = app
        self._lock = threading.RLock()

        # Active spinners by ID
        self._spinners: Dict[str, SpinnerInstance] = {}

        # Timer references
        self._textual_timer: Optional["Timer"] = None
        self._thread_timer: Optional[threading.Timer] = None

        # Animation loop state
        self._running = False

        # Per-spinner line tracking for parallel tool execution
        # Maps spinner_id -> line number where spinner was written
        self._spinner_lines: Dict[str, int] = {}
        # Maps spinner_id -> display text for rebuilding final line
        self._spinner_displays: Dict[str, Text] = {}
        # Maps spinner_id -> line number where result placeholder was written
        self._result_lines: Dict[str, int] = {}
        # Maps spinner_id -> line number where spacing placeholder was written
        self._spacing_lines: Dict[str, int] = {}
        # Maps spinner_id -> tip text for this spinner
        self._spinner_tips: Dict[str, str] = {}
        # Maps spinner_id -> line number where tip was written
        self._spinner_tip_lines: Dict[str, int] = {}
        # TipsManager for rotating tips below spinners
        self._tips_manager: Optional["TipsManager"] = None

    @property
    def _conversation(self) -> Optional["ConversationLog"]:
        """Get the conversation log widget."""
        return getattr(self.app, "conversation", None)

    def set_tips_manager(self, tips_manager: "TipsManager") -> None:
        """Set the TipsManager for tip display below spinners.

        Args:
            tips_manager: TipsManager instance for rotating tips
        """
        self._tips_manager = tips_manager

    # =========================================================================
    # FACADE API (for ui_callback compatibility)
    # =========================================================================

    def start(
        self,
        message: str | Text,
        spinner_type: SpinnerType = SpinnerType.TOOL,
        min_visible_ms: int = 0,
        skip_placeholder: bool = False,
    ) -> str:
        """Start a spinner and return its ID (FACADE API).

        This method tracks line numbers per spinner_id to support parallel
        tool execution. Each spinner gets its own line that can be updated
        independently when stop() is called.

        Args:
            message: The message to display with the spinner
            spinner_type: Type of spinner (TOOL or PROGRESS)
            min_visible_ms: Minimum time the spinner should be visible (in ms)
            skip_placeholder: If True, don't write placeholders (for bash commands)

        Returns:
            A unique spinner ID for later reference
        """
        conversation = self._conversation
        if conversation is None:
            return ""

        # Convert to Text if string
        if isinstance(message, str):
            display_text = Text(message, style=PRIMARY)
        else:
            display_text = message.copy()

        # Generate unique ID
        spinner_id = str(uuid.uuid4())[:8]

        # Store display text for later use in stop()
        self._spinner_displays[spinner_id] = display_text.copy()

        # Delegate to ConversationLog (BLOCKING to ensure line is added)
        # Track line number for this specific spinner
        def _start_on_ui():
            # Force-stop any deferred thinking spinner before recording line positions.
            # DefaultSpinnerManager.stop_spinner() defers removal via MIN_VISIBLE_MS timer.
            # If we record line positions while those spinner lines still exist, the later
            # timer-fired removal shifts lines without notifying SpinnerService, causing
            # stale indices in _spinner_lines → leftover blank line.
            if hasattr(conversation, "_spinner_manager"):
                sm = conversation._spinner_manager
                if sm._pending_stop_timer is not None:
                    sm._pending_stop_timer.stop()
                    sm._pending_stop_timer = None
                    sm._do_stop_spinner()
                elif sm._spinner_active:
                    sm._do_stop_spinner()

            # NOTE: Spacing before tool calls is handled by SpacingManager via add_tool_call().
            # Do NOT add unconditional blank lines here - it causes double spacing when
            # thinking blocks (which add trailing blanks) are followed by tool calls.
            if hasattr(conversation, "add_tool_call"):
                conversation.add_tool_call(display_text)
            # DON'T call start_tool_execution() - we manage animation ourselves
            # This prevents DefaultToolRenderer from overwriting parallel spinners

            # Get line number from tool_renderer's _tool_call_start
            # This is more reliable because RichLog.write() is async and len(lines)
            # might not update immediately. _tool_call_start is set BEFORE the async write.
            if hasattr(conversation, "_tool_renderer") and hasattr(
                conversation._tool_renderer, "_tool_call_start"
            ):
                line_num = conversation._tool_renderer._tool_call_start
            else:
                # Fallback: get the last line index
                line_num = len(conversation.lines) - 1

            # Store line number for this spinner
            self._spinner_lines[spinner_id] = line_num

            # Write tip line below spinner if TipsManager is available
            if self._tips_manager:
                tip = self._tips_manager.get_next_tip()
                if tip:
                    tip_line_num = len(conversation.lines)
                    tip_text = Text()
                    tip_text.append("  ⎿  Tip: ", style=GREY)
                    tip_text.append(tip, style=GREY)
                    conversation.write(tip_text)
                    self._spinner_tips[spinner_id] = tip
                    self._spinner_tip_lines[spinner_id] = tip_line_num

            # Write placeholders only for non-bash tools
            # Bash commands don't need placeholders - their output is rendered separately
            if not skip_placeholder:
                # Don't write result placeholder - we'll append the result line in stop()
                # This prevents an empty blank line from appearing during tool execution
                #
                # IMPORTANT: We do NOT write a spacing placeholder after the result.
                # Previously, we wrote TWO placeholders:
                #   1. Result placeholder (updated with result in stop())
                #   2. Spacing placeholder (blank line after result)
                #
                # This caused DOUBLE blank lines because:
                #   - Spacing placeholder added a blank line AFTER the result
                #   - message_renderer.add_user_message() adds a blank line BEFORE next prompt
                #
                # Now spacing is handled ONLY by add_user_message(), which adds a blank
                # line before each user prompt (see message_renderer.py:33-34).
                # DO NOT add a spacing placeholder here - it will cause double spacing.
                #
                # Set to None to indicate we should append (not update) the result line in stop()
                self._result_lines[spinner_id] = None
            else:
                # Skip placeholder for bash commands - they render output separately
                self._result_lines[spinner_id] = None

        self._run_blocking(_start_on_ui)

        # Register with animation loop via Callback API
        # This allows each spinner to animate its own line independently
        def render_callback(frame: SpinnerFrame) -> None:
            self._render_facade_spinner(spinner_id, frame)

        config = SPINNER_CONFIGS[spinner_type]
        instance = SpinnerInstance(
            spinner_id=spinner_id,
            spinner_type=spinner_type,
            config=config,
            message=(
                display_text.copy() if isinstance(display_text, Text) else Text(str(display_text))
            ),
            render_callback=render_callback,
        )

        should_start_loop = False
        with self._lock:
            self._spinners[spinner_id] = instance
            if not self._running:
                should_start_loop = True

        # Start animation loop AFTER releasing lock to avoid deadlock
        # (_on_tick tries to acquire the same lock)
        if should_start_loop:
            self._start_animation_loop()

        # Render initial frame immediately and BLOCK until it's displayed
        # This ensures the user sees the spinner character right away, not the static bullet
        self._render_initial_frame_blocking(spinner_id, display_text)

        return spinner_id

    def update(self, spinner_id: str, message: str | Text) -> None:
        """Update the spinner message in-place (FACADE API).

        Args:
            spinner_id: The spinner ID returned by start()
            message: New message to display
        """
        conversation = self._conversation
        if conversation is None:
            return

        # Convert to Text if string
        if isinstance(message, str):
            display_text = Text(message, style=PRIMARY)
        else:
            display_text = message.copy()

        def _update_on_ui():
            if hasattr(conversation, "update_progress_text"):
                conversation.update_progress_text(display_text)

        self._run_non_blocking(_update_on_ui)

    def stop(
        self,
        spinner_id: str,
        success: bool = True,
        result_message: str = "",
    ) -> None:
        """Stop a spinner (FACADE API).

        Uses stored line number to update the correct line for this specific
        spinner, enabling parallel tool execution where multiple spinners
        can be stopped independently in any order.

        Args:
            spinner_id: The spinner ID
            success: Whether the operation succeeded (affects bullet color)
            result_message: Optional message to display as the result
        """
        # First, try to stop as a callback-based spinner
        with self._lock:
            if spinner_id in self._spinners:
                # Mark as stopped BEFORE deleting - prevents race with queued callbacks
                self._spinners[spinner_id].stop_requested = True
                del self._spinners[spinner_id]
                if not self._spinners:
                    self._stop_animation_loop()

        # Get stored line numbers and display for this spinner
        line_num = self._spinner_lines.pop(spinner_id, None)
        display_text = self._spinner_displays.pop(spinner_id, None)
        result_line_num = self._result_lines.pop(spinner_id, None)
        # NOTE: spacing_line_num is no longer used.
        # Spacing after results is now handled by message_renderer.add_user_message()
        # which adds a blank line BEFORE each user prompt. This prevents double spacing.
        # See start() method comments for full explanation.
        self._spacing_lines.pop(spinner_id, None)  # Clean up if any old entries exist
        # Get tip line number BEFORE popping (needed for deletion in _stop_on_ui)
        tip_line_num = self._spinner_tip_lines.pop(spinner_id, None)
        self._spinner_tips.pop(spinner_id, None)
        conversation = self._conversation
        if conversation is None:
            return

        def _stop_on_ui():
            nonlocal result_line_num

            # Call stop_tool_execution for animation timer cleanup
            if hasattr(conversation, "stop_tool_execution"):
                conversation.stop_tool_execution(success)

            # Convert Text to Strip helper
            def text_to_strip(text: Text):
                from rich.console import Console
                from textual.strip import Strip

                # Use actual conversation width instead of hardcoded 1000
                width = (
                    conversation.virtual_size.width
                    if hasattr(conversation, "virtual_size")
                    else 1000
                )
                console = Console(width=width, force_terminal=True, no_color=False)
                segments = list(text.render(console))
                return Strip(segments)

            # If we have a stored line number, directly update that specific line
            # This ensures parallel tools update their own lines correctly
            if line_num is not None and display_text is not None:
                if line_num < len(conversation.lines):
                    # Build the final line with success/failure bullet
                    # No leading spaces - matches tool_renderer.py format
                    # Green only for bullet, text preserves its own style (PRIMARY)
                    bullet_style = GREEN_BRIGHT if success else ERROR
                    final_line = Text()
                    final_line.append("⏺ ", style=bullet_style)
                    final_line.append_text(display_text)  # Preserves display_text's PRIMARY style

                    # Directly update the line at stored position
                    conversation.lines[line_num] = text_to_strip(final_line)

            # Delete tip line if it exists (inserted after spinner, before placeholders)
            if tip_line_num is not None and tip_line_num < len(conversation.lines):
                del conversation.lines[tip_line_num]
                # Sync block registry so stale blocks don't re-render on resize
                if hasattr(conversation, "_block_registry"):
                    conversation._block_registry.remove_lines_range(tip_line_num, 1)
                # Adjust indices for lines that came after the deleted tip line
                if result_line_num is not None:
                    result_line_num -= 1

            # Append result line if needed (non-bash tools only)
            # No placeholder was written in start(), so we append a new line here
            # Bash commands don't need result lines - they render output separately
            # result_line_num is now used as a flag (None = append, not None = was placeholder)
            if result_line_num is None and result_message:
                # Append new result line since no placeholder exists
                display_msg = result_message
                result_line = Text("  ⎿  ", style=GREY)
                result_line.append(display_msg, style=GREY)
                conversation.write(result_line)

            # Clear any pending spacing line since we no longer use spacing placeholders
            conversation._pending_spacing_line = None

            conversation.refresh()

        self._run_blocking(_stop_on_ui)

    # =========================================================================
    # CALLBACK API (for widgets that manage their own spinners)
    # =========================================================================

    def register(
        self,
        spinner_type: SpinnerType,
        render_callback: Callable[[SpinnerFrame], None],
        message: Optional[Text | str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a new spinner and return its ID (CALLBACK API).

        The spinner starts animating immediately. The render_callback will be
        invoked on each frame with SpinnerFrame data.

        Args:
            spinner_type: Type of spinner (determines chars, interval, style)
            render_callback: Called each frame with SpinnerFrame data
            message: Optional message to display with spinner
            metadata: Optional widget-specific data passed through to callback

        Returns:
            Unique spinner ID for later reference
        """
        spinner_id = str(uuid.uuid4())[:8]
        config = SPINNER_CONFIGS[spinner_type]

        # Convert message to Text if string
        if isinstance(message, str):
            msg_text = Text(message, style=PRIMARY)
        elif message is not None:
            msg_text = message.copy()
        else:
            msg_text = Text("")

        instance = SpinnerInstance(
            spinner_id=spinner_id,
            spinner_type=spinner_type,
            config=config,
            message=msg_text,
            metadata=metadata or {},
            render_callback=render_callback,
        )

        should_start_loop = False
        with self._lock:
            self._spinners[spinner_id] = instance
            if not self._running:
                should_start_loop = True

        # Start animation loop AFTER releasing lock to avoid deadlock
        if should_start_loop:
            self._start_animation_loop()

        # Render initial frame immediately
        self._render_frame(instance)

        return spinner_id

    def update_message(self, spinner_id: str, message: Text | str) -> None:
        """Update the message for an active spinner (CALLBACK API).

        Args:
            spinner_id: ID returned by register()
            message: New message to display
        """
        with self._lock:
            instance = self._spinners.get(spinner_id)
            if instance is None:
                return

            if isinstance(message, str):
                instance.message = Text(message, style=PRIMARY)
            else:
                instance.message = message.copy()

    def update_metadata(self, spinner_id: str, **kwargs: Any) -> None:
        """Update metadata fields for an active spinner (CALLBACK API).

        Args:
            spinner_id: ID returned by register()
            **kwargs: Key-value pairs to merge into metadata
        """
        with self._lock:
            instance = self._spinners.get(spinner_id)
            if instance is None:
                return
            instance.metadata.update(kwargs)

    def stop_all(self, immediate: bool = True, success: bool = False) -> None:
        """Stop all active spinners.

        Delegates to stop() per spinner, which handles line updates, tip
        deletion, and refresh correctly. This is safe from the UI thread
        because _run_blocking (used by stop()) detects the UI thread and
        calls directly instead of dispatching via call_from_thread.

        Args:
            immediate: If True, stop all immediately ignoring min visibility
            success: Whether to render green (True) or red (False) bullets
        """
        with self._lock:
            spinner_ids = list(self._spinners.keys())

        for sid in spinner_ids:
            self.stop(sid, success=success, result_message="")

    def is_active(self, spinner_id: str) -> bool:
        """Check if a spinner is currently active."""
        with self._lock:
            return spinner_id in self._spinners

    def get_active_count(self) -> int:
        """Return count of active spinners."""
        with self._lock:
            return len(self._spinners)

    def clear_all_tips(self) -> None:
        """Clear all tip lines from active spinners.

        This is called when the approval modal appears to prevent tips
        from being displayed alongside the approval prompt.
        """
        conversation = self._conversation
        if conversation is None:
            return

        def _clear_on_ui():
            # Build list of (spinner_id, tip_line_num) sorted by line number descending
            # so we can delete from bottom to top without index shifting issues
            tips_to_delete = []
            for spinner_id, tip_line_num in list(self._spinner_tip_lines.items()):
                if tip_line_num < len(conversation.lines):
                    tips_to_delete.append((spinner_id, tip_line_num))

            # Sort by line number descending
            tips_to_delete.sort(key=lambda x: x[1], reverse=True)

            # Delete each tip line and adjust result/spacing lines
            for spinner_id, tip_line_num in tips_to_delete:
                del conversation.lines[tip_line_num]
                # Sync block registry (deleting bottom-to-top, so indices stay valid)
                if hasattr(conversation, "_block_registry"):
                    conversation._block_registry.remove_lines_range(tip_line_num, 1)

                # Adjust result and spacing line indices for this spinner
                if spinner_id in self._result_lines:
                    val = self._result_lines[spinner_id]
                    if val is not None and val > tip_line_num:
                        self._result_lines[spinner_id] = val - 1
                if spinner_id in self._spacing_lines:
                    val = self._spacing_lines[spinner_id]
                    if val is not None and val > tip_line_num:
                        self._spacing_lines[spinner_id] = val - 1

            # Clear tip tracking
            self._spinner_tips.clear()
            self._spinner_tip_lines.clear()

            conversation.refresh()

        self._run_non_blocking(_clear_on_ui)

    # =========================================================================
    # THREAD HELPERS
    # =========================================================================

    def _run_blocking(self, func, *args, **kwargs) -> None:
        """Run a function on the UI thread, blocking until complete."""
        self.app.call_from_thread(func, *args, **kwargs)

    def _run_non_blocking(self, func, *args, **kwargs) -> None:
        """Run a function on the UI thread without blocking."""
        self.app.call_from_thread_nonblocking(func, *args, **kwargs)
