"""Session picker with fuzzy search overlay."""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static, Label


class SessionItem(Static):
    """A single session entry in the picker."""

    DEFAULT_CSS = """
    SessionItem {
        height: 3;
        padding: 0 1;
        border-bottom: solid $surface-lighten-2;
    }
    SessionItem:hover {
        background: $surface-lighten-1;
    }
    SessionItem.--selected {
        background: $accent;
        color: $text;
    }
    """

    def __init__(self, session_id: str, title: str, date: str, stats: str) -> None:
        super().__init__()
        self.session_id = session_id
        self._title = title
        self._date = date
        self._stats = stats

    def compose(self) -> ComposeResult:
        yield Label(f"[bold]{self._title}[/bold]  [dim]{self._date}[/dim]")
        yield Label(f"  [dim]{self._stats}[/dim]")


class SessionPicker(ModalScreen[Optional[str]]):
    """Modal session picker with fuzzy search."""

    BINDINGS = [
        Binding("escape", "dismiss_picker", "Close"),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select_session", "Select", show=False),
    ]

    DEFAULT_CSS = """
    SessionPicker {
        align: center middle;
    }
    #session-picker-container {
        width: 80;
        max-height: 30;
        background: $surface;
        border: solid $accent;
        padding: 1;
    }
    #session-search {
        margin-bottom: 1;
    }
    #session-list {
        height: 1fr;
    }
    """

    def __init__(self, sessions: list[dict]) -> None:
        super().__init__()
        self._sessions = sessions
        self._filtered: list[dict] = list(sessions)
        self._selected_idx = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="session-picker-container"):
            yield Label("[bold]Sessions[/bold]  [dim](type to filter)[/dim]")
            yield Input(placeholder="Search sessions...", id="session-search")
            with VerticalScroll(id="session-list"):
                for session in self._filtered:
                    sid = session.get("id", "?")
                    title = session.get("title") or f"Session {sid[:8]}"
                    date = session.get("date", "")
                    msgs = session.get("message_count", 0)
                    files = session.get("files", 0)
                    additions = session.get("additions", 0)
                    deletions = session.get("deletions", 0)
                    stats = f"{msgs} msgs"
                    if files:
                        stats += f" · {files} files (+{additions}/-{deletions})"
                    yield SessionItem(sid, title, date, stats)

    def on_mount(self) -> None:
        self.query_one("#session-search", Input).focus()
        self._update_selection()

    @on(Input.Changed, "#session-search")
    def _on_search_changed(self, event: Input.Changed) -> None:
        query = event.value.lower()
        self._filtered = [
            s
            for s in self._sessions
            if query in (s.get("title") or "").lower() or query in s.get("id", "").lower()
        ]
        self._selected_idx = 0
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        container = self.query_one("#session-list", VerticalScroll)
        container.remove_children()
        for session in self._filtered:
            sid = session.get("id", "?")
            title = session.get("title") or f"Session {sid[:8]}"
            date = session.get("date", "")
            msgs = session.get("message_count", 0)
            files = session.get("files", 0)
            additions = session.get("additions", 0)
            deletions = session.get("deletions", 0)
            stats = f"{msgs} msgs"
            if files:
                stats += f" · {files} files (+{additions}/-{deletions})"
            container.mount(SessionItem(sid, title, date, stats))
        self._update_selection()

    def _update_selection(self) -> None:
        items = self.query("SessionItem")
        for i, item in enumerate(items):
            item.set_class(i == self._selected_idx, "--selected")

    def action_cursor_up(self) -> None:
        if self._selected_idx > 0:
            self._selected_idx -= 1
            self._update_selection()

    def action_cursor_down(self) -> None:
        items = self.query("SessionItem")
        if self._selected_idx < len(items) - 1:
            self._selected_idx += 1
            self._update_selection()

    def action_select_session(self) -> None:
        if self._filtered and 0 <= self._selected_idx < len(self._filtered):
            self.dismiss(self._filtered[self._selected_idx].get("id"))
        else:
            self.dismiss(None)

    def action_dismiss_picker(self) -> None:
        self.dismiss(None)
