"""Status dialog showing integration health and session info."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static


class StatusSection(Static):
    """A section in the status dialog."""

    DEFAULT_CSS = """
    StatusSection {
        margin-bottom: 1;
        padding: 0 1;
    }
    """


class StatusDialog(ModalScreen[None]):
    """Modal dialog showing system status and integration health."""

    BINDINGS = [
        Binding("escape", "dismiss_dialog", "Close"),
        Binding("q", "dismiss_dialog", "Close"),
    ]

    DEFAULT_CSS = """
    StatusDialog {
        align: center middle;
    }
    #status-container {
        width: 70;
        max-height: 35;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }
    .status-header {
        text-style: bold;
        margin-bottom: 1;
    }
    .status-ok {
        color: green;
    }
    .status-warn {
        color: yellow;
    }
    .status-error {
        color: red;
    }
    """

    def __init__(
        self,
        model_info: dict[str, str] | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        session_info: dict[str, Any] | None = None,
        context_info: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._model_info = model_info or {}
        self._mcp_servers = mcp_servers or []
        self._session_info = session_info or {}
        self._context_info = context_info or {}

    def compose(self) -> ComposeResult:
        with Vertical(id="status-container"):
            yield Label("[bold]OpenDev Status[/bold]", classes="status-header")

            # Model info
            yield Label("[bold]Models[/bold]")
            for key, value in self._model_info.items():
                yield Label(f"  {key}: {value}")

            yield Label("")

            # MCP Servers
            yield Label("[bold]MCP Servers[/bold]")
            if self._mcp_servers:
                for server in self._mcp_servers:
                    name = server.get("name", "unknown")
                    status = server.get("status", "unknown")
                    tools = server.get("tool_count", 0)
                    if status == "connected":
                        indicator = "[green]●[/green]"
                    elif status == "error":
                        indicator = "[red]●[/red]"
                    else:
                        indicator = "[yellow]●[/yellow]"
                    yield Label(f"  {indicator} {name} ({tools} tools)")
            else:
                yield Label("  [dim]No MCP servers configured[/dim]")

            yield Label("")

            # Session info
            yield Label("[bold]Session[/bold]")
            for key, value in self._session_info.items():
                yield Label(f"  {key}: {value}")

            yield Label("")

            # Context info
            yield Label("[bold]Context[/bold]")
            for key, value in self._context_info.items():
                yield Label(f"  {key}: {value}")

            yield Label("")
            yield Label("[dim]Press Escape or Q to close[/dim]")

    def action_dismiss_dialog(self) -> None:
        self.dismiss(None)
