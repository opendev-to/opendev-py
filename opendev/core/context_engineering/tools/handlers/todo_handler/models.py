"""TodoItem data model."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TodoItem:
    """A todo/task item."""

    id: str
    title: str
    status: str  # "todo", "doing", or "done"
    active_form: str = ""  # Present continuous form for spinner display (e.g., "Running tests")
    log: str = ""
    expanded: bool = False
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()
