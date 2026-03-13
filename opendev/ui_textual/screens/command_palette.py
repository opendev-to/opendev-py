"""Command palette with fuzzy search for all available actions."""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static, Label


class CommandItem(Static):
    """A single command entry in the palette."""

    DEFAULT_CSS = """
    CommandItem {
        height: 2;
        padding: 0 1;
    }
    CommandItem:hover {
        background: $surface-lighten-1;
    }
    CommandItem.--selected {
        background: $accent;
        color: $text;
    }
    """

    def __init__(self, name: str, description: str, shortcut: str = "") -> None:
        super().__init__()
        self.command_name = name
        self._description = description
        self._shortcut = shortcut

    def compose(self) -> ComposeResult:
        shortcut_text = f"  [dim]{self._shortcut}[/dim]" if self._shortcut else ""
        yield Label(f"[bold]{self.command_name}[/bold]{shortcut_text}")
        yield Label(f"  [dim]{self._description}[/dim]")


# Default commands registered in the palette
DEFAULT_COMMANDS = [
    {"name": "/help", "description": "Show help and available commands", "shortcut": ""},
    {"name": "/clear", "description": "Clear conversation history", "shortcut": "Ctrl+L"},
    {"name": "/models", "description": "Open model picker", "shortcut": ""},
    {"name": "/sessions", "description": "Browse and switch sessions", "shortcut": "Ctrl+P"},
    {"name": "/mode", "description": "Toggle Normal/Plan mode", "shortcut": "Shift+Tab"},
    {"name": "/agents", "description": "List or create custom agents", "shortcut": ""},
    {"name": "/skills", "description": "List or create skills", "shortcut": ""},
    {"name": "/compact", "description": "Manually compact conversation context", "shortcut": ""},
    {"name": "/tasks", "description": "List background tasks", "shortcut": ""},
    {"name": "/quit", "description": "Exit OpenDev", "shortcut": "Ctrl+C"},
    {"name": "/status", "description": "Show integration status", "shortcut": ""},
    {"name": "/archive", "description": "Archive current session", "shortcut": ""},
    {
        "name": "Toggle todo panel",
        "description": "Show/hide the todo sidebar",
        "shortcut": "Ctrl+T",
    },
    {"name": "Interrupt", "description": "Stop current operation", "shortcut": "Escape"},
    {
        "name": "Cycle autonomy",
        "description": "Switch between Manual/Semi-Auto/Auto",
        "shortcut": "Ctrl+Shift+A",
    },
]


class CommandPalette(ModalScreen[Optional[str]]):
    """Modal command palette with fuzzy search."""

    BINDINGS = [
        Binding("escape", "dismiss_palette", "Close"),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select_command", "Select", show=False),
    ]

    DEFAULT_CSS = """
    CommandPalette {
        align: center middle;
    }
    #palette-container {
        width: 70;
        max-height: 25;
        background: $surface;
        border: solid $accent;
        padding: 1;
    }
    #palette-search {
        margin-bottom: 1;
    }
    #palette-list {
        height: 1fr;
    }
    """

    def __init__(self, extra_commands: list[dict] | None = None) -> None:
        super().__init__()
        self._all_commands = list(DEFAULT_COMMANDS)
        if extra_commands:
            self._all_commands.extend(extra_commands)
        self._filtered = list(self._all_commands)
        self._selected_idx = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-container"):
            yield Label("[bold]Command Palette[/bold]")
            yield Input(placeholder="Type a command...", id="palette-search")
            with VerticalScroll(id="palette-list"):
                for cmd in self._filtered:
                    yield CommandItem(
                        cmd["name"],
                        cmd.get("description", ""),
                        cmd.get("shortcut", ""),
                    )

    def on_mount(self) -> None:
        self.query_one("#palette-search", Input).focus()
        self._update_selection()

    @on(Input.Changed, "#palette-search")
    def _on_search_changed(self, event: Input.Changed) -> None:
        query = event.value.lower()
        self._filtered = [
            c
            for c in self._all_commands
            if query in c["name"].lower() or query in c.get("description", "").lower()
        ]
        self._selected_idx = 0
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        container = self.query_one("#palette-list", VerticalScroll)
        container.remove_children()
        for cmd in self._filtered:
            container.mount(
                CommandItem(cmd["name"], cmd.get("description", ""), cmd.get("shortcut", ""))
            )
        self._update_selection()

    def _update_selection(self) -> None:
        items = self.query("CommandItem")
        for i, item in enumerate(items):
            item.set_class(i == self._selected_idx, "--selected")

    def action_cursor_up(self) -> None:
        if self._selected_idx > 0:
            self._selected_idx -= 1
            self._update_selection()

    def action_cursor_down(self) -> None:
        if self._selected_idx < len(self._filtered) - 1:
            self._selected_idx += 1
            self._update_selection()

    def action_select_command(self) -> None:
        if self._filtered and 0 <= self._selected_idx < len(self._filtered):
            self.dismiss(self._filtered[self._selected_idx]["name"])
        else:
            self.dismiss(None)

    def action_dismiss_palette(self) -> None:
        self.dismiss(None)
