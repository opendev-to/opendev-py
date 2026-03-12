"""Debug panel widget showing runtime diagnostics."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static, Label


class DebugPanel(Static):
    """Collapsible debug panel showing runtime diagnostics.

    Toggle with Ctrl+D. Shows token breakdown, tool timings,
    LLM call stats, and MCP connection status.
    """

    DEFAULT_CSS = """
    DebugPanel {
        dock: bottom;
        height: auto;
        max-height: 15;
        background: $surface;
        border-top: solid $accent;
        padding: 0 1;
        display: none;
    }
    DebugPanel.--visible {
        display: block;
    }
    .debug-header {
        text-style: bold;
        color: $accent;
    }
    .debug-row {
        height: 1;
    }
    """

    is_visible = reactive(False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stats: dict[str, Any] = {}
        self._tool_timings: list[dict] = []
        self._llm_calls: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Label(
            "[bold]Debug Panel[/bold]  [dim](Ctrl+D to hide)[/dim]",
            classes="debug-header",
        )
        yield Static(id="debug-content")

    def toggle(self) -> None:
        """Toggle panel visibility."""
        self.is_visible = not self.is_visible
        self.set_class(self.is_visible, "--visible")
        if self.is_visible:
            self._refresh_content()

    def update_stats(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_cost: float = 0.0,
        context_pct: float = 0.0,
        llm_calls: int = 0,
        tool_calls: int = 0,
        mcp_servers: int = 0,
        mcp_connected: int = 0,
    ) -> None:
        """Update debug statistics."""
        self._stats = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost": total_cost,
            "context_pct": context_pct,
            "llm_calls": llm_calls,
            "tool_calls": tool_calls,
            "mcp_servers": mcp_servers,
            "mcp_connected": mcp_connected,
        }
        if self.is_visible:
            self._refresh_content()

    def record_tool_timing(self, tool_name: str, duration_ms: float) -> None:
        """Record a tool execution timing."""
        self._tool_timings.append({"name": tool_name, "duration_ms": duration_ms})
        # Keep last 20
        if len(self._tool_timings) > 20:
            self._tool_timings = self._tool_timings[-20:]
        if self.is_visible:
            self._refresh_content()

    def record_llm_call(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: float,
    ) -> None:
        """Record an LLM call."""
        self._llm_calls.append(
            {
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "duration_ms": duration_ms,
            }
        )
        if len(self._llm_calls) > 10:
            self._llm_calls = self._llm_calls[-10:]
        if self.is_visible:
            self._refresh_content()

    def _refresh_content(self) -> None:
        """Refresh the debug content display."""
        content = self.query_one("#debug-content", Static)

        lines = []
        s = self._stats

        # Token breakdown
        inp = s.get("input_tokens", 0)
        out = s.get("output_tokens", 0)
        cost = s.get("total_cost", 0.0)
        ctx = s.get("context_pct", 0.0)
        lines.append(
            f"[bold]Tokens:[/bold] in={inp:,} out={out:,} "
            f"total={inp + out:,}  "
            f"[bold]Cost:[/bold] ${cost:.4f}  "
            f"[bold]Context:[/bold] {ctx:.1f}%"
        )

        # LLM & Tool stats
        llm = s.get("llm_calls", 0)
        tools = s.get("tool_calls", 0)
        mcp_s = s.get("mcp_servers", 0)
        mcp_c = s.get("mcp_connected", 0)
        lines.append(
            f"[bold]LLM calls:[/bold] {llm}  "
            f"[bold]Tool calls:[/bold] {tools}  "
            f"[bold]MCP:[/bold] {mcp_c}/{mcp_s} connected"
        )

        # Recent tool timings
        if self._tool_timings:
            recent = self._tool_timings[-5:]
            timing_parts = [f"{t['name']}={t['duration_ms']:.0f}ms" for t in recent]
            lines.append(f"[bold]Recent tools:[/bold] {', '.join(timing_parts)}")

        # Recent LLM calls
        if self._llm_calls:
            last = self._llm_calls[-1]
            lines.append(
                f"[bold]Last LLM:[/bold] {last['model']} "
                f"({last['prompt_tokens']}->{last['completion_tokens']} tok, "
                f"{last['duration_ms']:.0f}ms)"
            )

        content.update("\n".join(lines))
