"""Resize coordination methods for spinner service."""

from __future__ import annotations


class ResizeMixin:
    """Mixin for resize coordination.

    Expects the host class to provide:
    - self._lock: threading.RLock
    - self._spinners: Dict[str, SpinnerInstance]
    - self._running: bool
    - self._spinner_lines: Dict[str, int]
    - self._result_lines: Dict[str, int]
    - self._spacing_lines: Dict[str, int]
    - self._spinner_tip_lines: Dict[str, int]
    - self._stop_animation_loop(): method
    - self._schedule_tick(): method
    """

    def pause_for_resize(self) -> None:
        """Stop animation timers for resize."""
        with self._lock:
            self._stop_animation_loop()

    def adjust_indices(self, delta: int, first_affected: int) -> None:
        """Adjust all tracked line indices by delta.

        Args:
            delta: Number of lines added (positive) or removed (negative)
            first_affected: First line index affected by the change
        """
        with self._lock:
            # Adjust spinner lines
            for spinner_id in list(self._spinner_lines.keys()):
                line = self._spinner_lines[spinner_id]
                if line >= first_affected:
                    self._spinner_lines[spinner_id] = line + delta

            # Adjust result lines
            for spinner_id in list(self._result_lines.keys()):
                line = self._result_lines[spinner_id]
                if line is not None and line >= first_affected:
                    self._result_lines[spinner_id] = line + delta

            # Adjust spacing lines
            for spinner_id in list(self._spacing_lines.keys()):
                line = self._spacing_lines[spinner_id]
                if line is not None and line >= first_affected:
                    self._spacing_lines[spinner_id] = line + delta

            # Adjust tip lines
            for spinner_id in list(self._spinner_tip_lines.keys()):
                line = self._spinner_tip_lines[spinner_id]
                if line >= first_affected:
                    self._spinner_tip_lines[spinner_id] = line + delta

    def resume_after_resize(self) -> None:
        """Restart animation loop after resize."""
        with self._lock:
            if self._spinners and not self._running:
                self._running = True
        # Start animation loop outside lock to avoid deadlock
        if self._spinners:
            self._schedule_tick()
