"""Mixin for bash output boxes, streaming, and plan content."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text

from opendev.ui_textual.style_tokens import (
    ERROR,
    GREY,
    SUBTLE,
)
from opendev.ui_textual.utils.output_summarizer import summarize_output, get_expansion_hint

if TYPE_CHECKING:
    pass


class BashOutputMixin:
    """Bash output box rendering, streaming, and plan content display."""

    # Attributes expected from DefaultToolRenderer.__init__:
    #   log, _spacing, _box_renderer, _streaming_box_header_line,
    #   _streaming_box_top_line, _streaming_box_command,
    #   _streaming_box_working_dir, _streaming_box_content_lines,
    #   _streaming_box_config, _collapsible_outputs, _most_recent_collapsible,
    #   _truncate_from (method from main class)

    # --- Bash Box Output ---

    def add_bash_output_box(
        self,
        output: str,
        is_error: bool = False,
        command: str = "",
        working_dir: str = ".",
        depth: int = 0,
    ) -> None:
        """Render bash output with collapsible support for long output."""
        lines = output.rstrip("\n").splitlines()
        if not lines:
            lines = ["Completed"]

        if depth == 0:
            head_count = self._box_renderer.MAIN_AGENT_HEAD_LINES
            tail_count = self._box_renderer.MAIN_AGENT_TAIL_LINES
        else:
            head_count = self._box_renderer.SUBAGENT_HEAD_LINES
            tail_count = self._box_renderer.SUBAGENT_TAIL_LINES

        max_lines = head_count + tail_count
        should_collapse = len(lines) > max_lines

        indent = "  " * depth

        if should_collapse:
            start_line = len(self.log.lines)

            summary = summarize_output(lines, "bash")
            hint = get_expansion_hint()
            summary_line = Text(f"{indent}  \u23bf  ", style=GREY)
            summary_line.append(summary, style=SUBTLE)
            summary_line.append(f" {hint}", style=f"{SUBTLE} italic")
            self.log.write(summary_line, wrappable=False)

            end_line = len(self.log.lines) - 1

            from opendev.ui_textual.models.collapsible_output import CollapsibleOutput

            collapsible = CollapsibleOutput(
                start_line=start_line,
                end_line=end_line,
                full_content=lines,
                summary=summary,
                is_expanded=False,
                output_type="bash",
                command=command,
                working_dir=working_dir,
                is_error=is_error,
                depth=depth,
            )
            self._collapsible_outputs[start_line] = collapsible
            self._most_recent_collapsible = start_line
        else:
            is_first = True
            for line in lines:
                self._write_bash_output_line(line, indent, is_error, is_first)
                is_first = False

        self._spacing.after_bash_output_box()

    def _write_bash_output_line(
        self, line: str, indent: str, is_error: bool, is_first: bool = False
    ) -> None:
        """Write a single bash output line with proper indentation."""
        normalized = self._box_renderer.normalize_line(line)
        prefix = f"{indent}  \u23bf  " if is_first else f"{indent}     "
        output_line = Text(prefix, style=GREY)
        output_line.append(normalized, style=ERROR if is_error else GREY)
        self.log.write(output_line, wrappable=False)

    def add_plan_content_box(self, plan_content: str) -> None:
        """Render plan content in a bordered Markdown panel."""
        from rich.markdown import Markdown
        from rich.panel import Panel

        md = Markdown(plan_content)
        panel = Panel(md, title="Plan", border_style="bright_cyan", padding=(1, 2))
        self.log.write(panel, wrappable=False)

    def start_streaming_bash_box(self, command: str = "", working_dir: str = ".") -> None:
        """Start streaming bash output with minimal style."""
        self._streaming_box_command = command
        self._streaming_box_working_dir = working_dir
        self._streaming_box_content_lines = []

        self._streaming_box_top_line = len(self.log.lines)
        self._streaming_box_header_line = len(self.log.lines)

    def append_to_streaming_box(self, line: str, is_stderr: bool = False) -> None:
        """Append a content line to the streaming output."""
        if self._streaming_box_header_line is None:
            return

        is_first = len(self._streaming_box_content_lines) == 0

        self._streaming_box_content_lines.append((line, is_stderr))
        self._write_bash_output_line(line, "", is_stderr, is_first)

    def close_streaming_bash_box(self, is_error: bool, exit_code: int) -> None:
        """Close streaming bash output, collapsing if it exceeds threshold."""
        content_lines = [line for line, _ in self._streaming_box_content_lines]
        head_count = self._box_renderer.MAIN_AGENT_HEAD_LINES
        tail_count = self._box_renderer.MAIN_AGENT_TAIL_LINES
        max_lines = head_count + tail_count

        if len(content_lines) > max_lines and self._streaming_box_top_line is not None:
            self._rebuild_streaming_box_as_collapsed(is_error, content_lines)

        self._streaming_box_header_line = None
        self._streaming_box_top_line = None
        self._streaming_box_config = None
        self._streaming_box_command = ""
        self._streaming_box_working_dir = "."
        self._streaming_box_content_lines = []

    def _rebuild_streaming_box_as_collapsed(
        self,
        is_error: bool,
        content_lines: list[str],
    ) -> None:
        """Rebuild streaming output as a collapsed summary."""
        if self._streaming_box_top_line is None:
            return

        self._truncate_from(self._streaming_box_top_line)

        start_line = len(self.log.lines)

        summary = summarize_output(content_lines, "bash")
        hint = get_expansion_hint()
        summary_line = Text("  \u23bf  ", style=GREY)
        summary_line.append(summary, style=SUBTLE)
        summary_line.append(f" {hint}", style=f"{SUBTLE} italic")
        self.log.write(summary_line, wrappable=False)

        end_line = len(self.log.lines) - 1

        from opendev.ui_textual.models.collapsible_output import CollapsibleOutput

        collapsible = CollapsibleOutput(
            start_line=start_line,
            end_line=end_line,
            full_content=content_lines,
            summary=summary,
            is_expanded=False,
            output_type="bash",
            command=self._streaming_box_command,
            working_dir=self._streaming_box_working_dir,
            is_error=is_error,
            depth=0,
        )
        self._collapsible_outputs[start_line] = collapsible
        self._most_recent_collapsible = start_line

    def _rebuild_streaming_box_with_truncation(
        self,
        is_error: bool,
        content_lines: list[str],
    ) -> None:
        """Rebuild the streaming output with head+tail truncation."""
        if self._streaming_box_top_line is None:
            return

        self._truncate_from(self._streaming_box_top_line)

        head_count = self._box_renderer.MAIN_AGENT_HEAD_LINES
        tail_count = self._box_renderer.MAIN_AGENT_TAIL_LINES
        head_lines, tail_lines, hidden_count = self._box_renderer.truncate_lines_head_tail(
            content_lines, head_count, tail_count
        )

        is_first = True
        for line in head_lines:
            self._write_bash_output_line(line, "", is_error, is_first)
            is_first = False

        if hidden_count > 0:
            hidden_text = Text(
                f"       ... {hidden_count} lines hidden ...", style=f"{SUBTLE} italic"
            )
            self.log.write(hidden_text, wrappable=False)

        for line in tail_lines:
            self._write_bash_output_line(line, "", is_error, is_first)
            is_first = False

    def add_nested_bash_output_box(
        self,
        output: str,
        is_error: bool = False,
        command: str = "",
        working_dir: str = "",
        depth: int = 1,
    ) -> None:
        """Render nested bash output with minimal style."""
        self.add_bash_output_box(output, is_error, command, working_dir, depth)
