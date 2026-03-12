"""Mixin for collapsible output toggle/expand/collapse."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Tuple

from rich.text import Text

from opendev.ui_textual.style_tokens import GREY, SUBTLE
from opendev.ui_textual.utils.output_summarizer import get_expansion_hint

if TYPE_CHECKING:
    from opendev.ui_textual.models.collapsible_output import CollapsibleOutput


class CollapsibleMixin:
    """Collapsible output toggle, expand, and collapse operations."""

    # Attributes expected from DefaultToolRenderer.__init__:
    #   log, _collapsible_outputs, _most_recent_collapsible,
    #   _write_bash_output_line (method from BashOutputMixin)

    # --- Collapsible Output Toggle Methods ---

    def toggle_most_recent_collapsible(self) -> Tuple[bool, int, int]:
        """Toggle the most recent collapsible output region.

        Returns:
            Tuple of (toggled, delta, first_affected).
        """
        if self._most_recent_collapsible is None:
            return (False, 0, 0)

        collapsible = self._collapsible_outputs.get(self._most_recent_collapsible)
        if collapsible is None:
            return (False, 0, 0)

        return self._toggle_collapsible(collapsible)

    def toggle_output_at_line(self, line_index: int) -> Tuple[bool, int, int]:
        """Toggle collapsible output containing the given line.

        Args:
            line_index: Line index in the conversation log.

        Returns:
            Tuple of (toggled, delta, first_affected).
        """
        for start, collapsible in self._collapsible_outputs.items():
            if collapsible.contains_line(line_index):
                return self._toggle_collapsible(collapsible)
        return (False, 0, 0)

    def _toggle_collapsible(self, collapsible: "CollapsibleOutput") -> Tuple[bool, int, int]:
        """Toggle a specific collapsible output region.

        Args:
            collapsible: CollapsibleOutput to toggle.

        Returns:
            Tuple of (toggled, delta, first_affected).
        """
        old_start = collapsible.start_line
        old_end = collapsible.end_line
        old_count = old_end - old_start + 1
        if collapsible.is_expanded:
            self._collapse_output(collapsible)
        else:
            self._expand_output(collapsible)
        new_count = collapsible.end_line - collapsible.start_line + 1
        delta = new_count - old_count
        return (True, delta, old_start)

    def _expand_output(self, collapsible: "CollapsibleOutput") -> None:
        """Expand a collapsed output region to show full content."""
        old_start = collapsible.start_line
        old_end = collapsible.end_line

        after_lines = list(self.log.lines[old_end + 1 :])

        del self.log.lines[old_start:]

        if hasattr(self.log, "_block_registry"):
            self.log._block_registry.remove_blocks_from(old_start)

        if hasattr(self.log, "_line_cache"):
            self.log._line_cache.clear()

        indent = "  " * collapsible.depth
        new_start = len(self.log.lines)
        is_first = True
        for line in collapsible.full_content:
            self._write_bash_output_line(line, indent, collapsible.is_error, is_first)
            is_first = False
        new_end = len(self.log.lines) - 1
        new_count = new_end - new_start + 1
        old_count = old_end - old_start + 1

        self.log.lines.extend(after_lines)

        collapsible.is_expanded = True
        if collapsible.start_line in self._collapsible_outputs:
            del self._collapsible_outputs[collapsible.start_line]
        collapsible.start_line = new_start
        collapsible.end_line = new_end
        self._collapsible_outputs[new_start] = collapsible
        self._most_recent_collapsible = new_start

        delta = new_count - old_count
        if delta != 0:
            shifted = {}
            for key, c in list(self._collapsible_outputs.items()):
                if c is not collapsible and key > old_start:
                    del self._collapsible_outputs[key]
                    c.start_line += delta
                    c.end_line += delta
                    shifted[c.start_line] = c
            self._collapsible_outputs.update(shifted)

        if hasattr(self.log, "_recalculate_virtual_size"):
            self.log._recalculate_virtual_size()
        self.log.refresh()

    def _collapse_output(self, collapsible: "CollapsibleOutput") -> None:
        """Collapse an expanded output region to show just summary."""
        old_start = collapsible.start_line
        old_end = collapsible.end_line

        after_lines = list(self.log.lines[old_end + 1 :])

        del self.log.lines[old_start:]

        if hasattr(self.log, "_block_registry"):
            self.log._block_registry.remove_blocks_from(old_start)

        if hasattr(self.log, "_line_cache"):
            self.log._line_cache.clear()

        indent = "  " * collapsible.depth
        new_start = len(self.log.lines)
        hint = get_expansion_hint()
        summary_line = Text(f"{indent}  \u23bf  ", style=GREY)
        summary_line.append(collapsible.summary, style=SUBTLE)
        summary_line.append(f" {hint}", style=f"{SUBTLE} italic")
        self.log.write(summary_line, wrappable=False)
        new_end = len(self.log.lines) - 1
        new_count = new_end - new_start + 1
        old_count = old_end - old_start + 1

        self.log.lines.extend(after_lines)

        collapsible.is_expanded = False
        if collapsible.start_line in self._collapsible_outputs:
            del self._collapsible_outputs[collapsible.start_line]
        collapsible.start_line = new_start
        collapsible.end_line = new_end
        self._collapsible_outputs[new_start] = collapsible
        self._most_recent_collapsible = new_start

        delta = new_count - old_count
        if delta != 0:
            shifted = {}
            for key, c in list(self._collapsible_outputs.items()):
                if c is not collapsible and key > old_start:
                    del self._collapsible_outputs[key]
                    c.start_line += delta
                    c.end_line += delta
                    shifted[c.start_line] = c
            self._collapsible_outputs.update(shifted)

        if hasattr(self.log, "_recalculate_virtual_size"):
            self.log._recalculate_virtual_size()
        self.log.refresh()

    def has_collapsible_output(self) -> bool:
        """Check if there are any collapsible output regions.

        Returns:
            True if at least one collapsible region exists.
        """
        return len(self._collapsible_outputs) > 0

    def get_collapsible_at_line(self, line_index: int) -> Optional["CollapsibleOutput"]:
        """Get collapsible output at a specific line.

        Args:
            line_index: Line index to check.

        Returns:
            CollapsibleOutput if found, None otherwise.
        """
        for collapsible in self._collapsible_outputs.values():
            if collapsible.contains_line(line_index):
                return collapsible
        return None
