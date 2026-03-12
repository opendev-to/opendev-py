"""Animation loop and rendering for spinners."""

from __future__ import annotations

import threading
import time
from rich.text import Text

from opendev.ui_textual.style_tokens import GREY
from opendev.ui_textual.managers.spinner_service.models import (
    SpinnerFrame,
    SpinnerInstance,
    SpinnerType,
    SPINNER_CONFIGS,
)


class AnimationMixin:
    """Mixin for animation loop management.

    Expects the host class to provide:
    - self.app: textual App instance
    - self._lock: threading.RLock
    - self._spinners: Dict[str, SpinnerInstance]
    - self._running: bool
    - self._textual_timer: Optional[Timer]
    - self._thread_timer: Optional[threading.Timer]
    - self._spinner_lines: Dict[str, int]
    - self._spinner_displays: Dict[str, Text]
    - self._conversation: property returning ConversationLog
    - self._run_blocking(): method
    - self._run_non_blocking(): method
    """

    # Tick interval - GCD of all spinner intervals for smooth animation
    _TICK_INTERVAL_MS = 60  # ~16fps base rate, divides evenly into 120, 300, 150

    def _start_animation_loop(self) -> None:
        """Start the animation loop (called WITHOUT lock held to avoid deadlock)."""
        with self._lock:
            if self._running:
                return
            self._running = True

        # Schedule tick OUTSIDE lock to avoid deadlock
        # (_on_tick also acquires the lock)
        self._schedule_tick()

    def _stop_animation_loop(self) -> None:
        """Stop the animation loop (called with lock held)."""
        self._running = False

        if self._textual_timer is not None:
            self._textual_timer.stop()
            self._textual_timer = None

        if self._thread_timer is not None:
            self._thread_timer.cancel()
            self._thread_timer = None

    def _schedule_tick(self) -> None:
        """Schedule next animation tick using dual-timer pattern."""
        if not self._running:
            return

        interval_sec = self._TICK_INTERVAL_MS / 1000

        # Cancel existing timers (thread-safe operations)
        if self._textual_timer is not None:
            try:
                self._textual_timer.stop()
            except Exception:
                pass
        if self._thread_timer is not None:
            self._thread_timer.cancel()
            self._thread_timer = None

        # Schedule Textual timer - MUST be done on UI thread
        def _setup_textual_timer():
            try:
                self._textual_timer = self.app.set_timer(interval_sec, self._on_tick)
            except Exception:
                pass  # App may be shutting down

        # Dispatch to UI thread (non-blocking)
        self._run_non_blocking(_setup_textual_timer)

        # Schedule threading.Timer fallback (bypasses blocked event loop)
        self._thread_timer = threading.Timer(interval_sec, self._on_thread_tick)
        self._thread_timer.daemon = True
        self._thread_timer.start()

    def _on_thread_tick(self) -> None:
        """Fallback tick via threading.Timer when event loop is blocked."""
        if not self._running:
            return

        # Use call_from_thread to safely run on UI thread
        try:
            self.app.call_from_thread(self._on_tick)
        except Exception:
            pass  # App may be shutting down

    def _on_tick(self) -> None:
        """Animation tick - advance frames and render as needed."""
        # Cancel thread timer if this tick came from Textual timer
        if self._thread_timer is not None:
            self._thread_timer.cancel()
            self._thread_timer = None

        now = time.monotonic()

        with self._lock:
            if not self._running:
                return

            # Process each active spinner
            to_remove: list[str] = []
            to_render: list[SpinnerInstance] = []

            for spinner_id, instance in self._spinners.items():
                # Check for delayed stop
                if instance.stop_requested:
                    elapsed_ms = (now - instance.started_at) * 1000
                    if elapsed_ms >= instance.config.min_visible_ms:
                        to_remove.append(spinner_id)
                        continue

                # Check if this spinner is due for a frame update
                elapsed_since_frame = (now - instance.last_frame_at) * 1000
                if elapsed_since_frame >= instance.config.interval_ms:
                    # Advance frame
                    instance.frame_index = (instance.frame_index + 1) % len(instance.config.chars)
                    instance.last_frame_at = now

                    # Mark for rendering (outside lock)
                    to_render.append(instance)

            # Remove stopped spinners
            for spinner_id in to_remove:
                del self._spinners[spinner_id]

            # Stop loop if no spinners left
            if not self._spinners:
                self._stop_animation_loop()
                return

        # Render frames (outside lock to avoid deadlock)
        for instance in to_render:
            self._render_frame(instance)

        # Schedule next tick
        self._schedule_tick()

    def _render_frame(self, instance: SpinnerInstance) -> None:
        """Invoke the render callback for a spinner."""
        # Race condition prevention: don't render if stop was requested
        # This guards against callbacks firing after stop() but before the instance
        # is fully cleaned up from the to_render list in _on_tick()
        if instance.stop_requested:
            return

        if instance.render_callback is None:
            return

        frame = SpinnerFrame(
            spinner_id=instance.spinner_id,
            spinner_type=instance.spinner_type,
            char=instance.config.chars[instance.frame_index],
            frame_index=instance.frame_index,
            elapsed_seconds=int(time.monotonic() - instance.started_at),
            message=instance.message.copy(),
            style=instance.config.style,
            metadata=instance.metadata.copy(),
        )

        try:
            instance.render_callback(frame)
        except Exception:
            pass  # Don't let callback errors crash the loop

    def _render_initial_frame_blocking(self, spinner_id: str, display_text: Text) -> None:
        """Render the initial spinner frame with blocking call.

        This ensures the first frame is visible immediately before start() returns.
        Uses the first animation character with elapsed time of 0.

        Args:
            spinner_id: The spinner ID
            display_text: The display text for the spinner
        """
        line_num = self._spinner_lines.get(spinner_id)
        if line_num is None:
            return

        conversation = self._conversation
        if conversation is None:
            return

        config = SPINNER_CONFIGS[SpinnerType.TOOL]

        def _update_on_ui():
            try:
                if line_num >= len(conversation.lines):
                    return

                # Build initial animated line: "⠋ Tool description (0s)"
                formatted = Text()
                formatted.append(f"{config.chars[0]} ", style=config.style)
                formatted.append_text(display_text)
                formatted.append(" (0s)", style=GREY)

                # Convert to Strip
                from rich.console import Console
                from textual.strip import Strip

                # Use actual conversation width
                width = (
                    conversation.virtual_size.width
                    if hasattr(conversation, "virtual_size")
                    else 1000
                )
                console = Console(width=width, force_terminal=True, no_color=False)
                segments = list(formatted.render(console))
                strip = Strip(segments)

                # STRATEGY: Delete & Insert to force update
                if line_num < len(conversation.lines):
                    del conversation.lines[line_num]
                    conversation.lines.insert(line_num, strip)

                # Invalidate cache and refresh - BOTH refreshes are needed
                if hasattr(conversation, "refresh_line"):
                    conversation.refresh_line(line_num)
                else:
                    conversation.refresh()

                # Also refresh the app (like DefaultSpinnerManager does)
                if hasattr(self.app, "refresh"):
                    self.app.refresh()
            except Exception:
                pass  # Silently ignore errors

        # BLOCKING call to ensure initial frame is visible before returning
        self._run_blocking(_update_on_ui)

    def _render_facade_spinner(self, spinner_id: str, frame: SpinnerFrame) -> None:
        """Render a facade-API spinner by updating its specific line.

        This method updates the spinner line in-place, allowing parallel spinners
        to animate independently without overwriting each other.

        Args:
            spinner_id: The spinner ID to render
            frame: The current animation frame data
        """
        line_num = self._spinner_lines.get(spinner_id)
        display_text = self._spinner_displays.get(spinner_id)

        if line_num is None or display_text is None:
            return

        conversation = self._conversation
        if conversation is None:
            return

        def _update_on_ui():
            try:
                if line_num >= len(conversation.lines):
                    return

                # Build animated line: "⠋ Tool description (5s)"
                elapsed = frame.elapsed_seconds
                formatted = Text()
                formatted.append(f"{frame.char} ", style=frame.style)
                formatted.append_text(display_text)
                formatted.append(f" ({elapsed}s)", style=GREY)

                # Convert to Strip
                from rich.console import Console
                from textual.strip import Strip

                # Use actual conversation width
                width = (
                    conversation.virtual_size.width
                    if hasattr(conversation, "virtual_size")
                    else 1000
                )
                console = Console(width=width, force_terminal=True, no_color=False)
                segments = list(formatted.render(console))
                strip = Strip(segments)

                # STRATEGY: Delete & Insert to force RichLog/Textual to recognize update
                # (same approach as DefaultSpinnerManager)
                if line_num < len(conversation.lines):
                    del conversation.lines[line_num]
                    conversation.lines.insert(line_num, strip)

                # Invalidate cache and refresh - BOTH refreshes are needed
                if hasattr(conversation, "refresh_line"):
                    conversation.refresh_line(line_num)
                else:
                    conversation.refresh()

                # Also refresh the app (like DefaultSpinnerManager does)
                if hasattr(self.app, "refresh"):
                    self.app.refresh()
            except Exception:
                pass  # Silently ignore errors in animation update

        # Run on UI thread (handles both UI thread and background thread cases)
        self._run_non_blocking(_update_on_ui)
