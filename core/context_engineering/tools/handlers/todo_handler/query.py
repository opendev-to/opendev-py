"""Query and listing operations for todo items."""

import logging
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from opendev.core.context_engineering.tools.handlers.todo_handler.models import TodoItem

logger = logging.getLogger(__name__)


class QueryMixin:
    """Mixin providing list/query/formatting operations."""

    def list_todos(self) -> dict:
        """List all todos with formatted display.

        Returns:
            Result dict with success status and formatted output
        """
        if not self._todos:
            return {
                "success": True,
                "output": "No todos found. Create one with create_todo().",
                "todos": [],
            }

        # Sort by status (doing -> todo -> done) then by ID
        status_order = {"doing": 0, "todo": 1, "done": 2}

        def extract_id_number(todo_id: str) -> int:
            """Extract numeric part from 'todo-X' format."""
            if todo_id.startswith("todo-"):
                return int(todo_id[5:])
            return int(todo_id)

        sorted_todos = sorted(
            self._todos.values(),
            key=lambda t: (status_order.get(t.status, 3), extract_id_number(t.id)),
        )

        lines = []
        for todo in sorted_todos:
            if todo.status == "done":
                lines.append(f"✓ [{todo.id}] {todo.title}")
            elif todo.status == "doing":
                lines.append(f"▶ [{todo.id}] {todo.title}")
            else:
                lines.append(f"○ [{todo.id}] {todo.title}")
        output = "\n".join(lines) if lines else "No todos."

        return {
            "success": True,
            "output": output,
            "todos": [asdict(t) for t in sorted_todos],
            "count": len(self._todos),
        }

    def _format_todo_list_simple(self) -> list[str]:
        """Format todo list for display after updates.

        Returns:
            List of formatted todo lines with status indicators and strikethrough for completed items.
        """
        if not self._todos:
            return []

        lines = []
        status_order = {"doing": 0, "todo": 1, "done": 2}

        def extract_id_number(todo_id: str) -> int:
            """Extract numeric part from 'todo-X' format."""
            if todo_id.startswith("todo-"):
                return int(todo_id[5:])
            return int(todo_id)

        sorted_todos = sorted(
            self._todos.values(),
            key=lambda t: (status_order.get(t.status, 3), extract_id_number(t.id)),
        )

        for todo in sorted_todos:
            if todo.status == "done":
                # Completed: green with strikethrough
                lines.append(f"  [green]✓ ~~{todo.title}~~[/green]")
            elif todo.status == "doing":
                # In progress: yellow
                lines.append(f"  [yellow]▶ {todo.title}[/yellow]")
            else:
                # Pending: cyan
                lines.append(f"  [cyan]○ {todo.title}[/cyan]")

        return lines

    def _is_status_only_update(self, new_todos: list) -> bool:
        """Check if new todos have same content as existing, just different statuses.

        This detects when write_todos is called with the same todo list but only
        status changes (e.g., marking one item as in_progress).

        Args:
            new_todos: Normalized todo list (list of strings or tuples)

        Returns:
            True if content matches existing todos and only statuses differ
        """
        if len(new_todos) != len(self._todos):
            return False

        existing_titles = [t.title for t in self._todos.values()]
        new_titles = []
        for item in new_todos:
            if isinstance(item, tuple):
                new_titles.append(item[0])
            else:
                new_titles.append(str(item))

        return existing_titles == new_titles

    def _apply_status_updates(self, new_todos: list) -> dict:
        """Update only the statuses without recreating todos.

        This is called when write_todos detects a status-only update,
        avoiding the overhead of clearing and recreating all todos.

        Args:
            new_todos: Normalized todo list with new statuses

        Returns:
            Result dict with minimal output
        """
        updated = []
        for i, (todo_id, todo) in enumerate(self._todos.items()):
            if i < len(new_todos):
                item = new_todos[i]
                if isinstance(item, tuple) and len(item) >= 2:
                    new_status = item[1]
                    new_active_form = item[2] if len(item) >= 3 else ""
                    if todo.status != new_status:
                        todo.status = new_status
                        if new_active_form:
                            todo.active_form = self._strip_markdown(new_active_form)
                        todo.updated_at = datetime.now().isoformat()
                        updated.append(todo.title)

                        # ENFORCEMENT: Ensure only one todo can be "doing" at a time
                        if new_status == "doing":
                            for other_id, other_todo in self._todos.items():
                                if other_id != todo_id and other_todo.status == "doing":
                                    other_todo.status = "todo"

        if updated:
            # Return minimal output - just note the update
            return {
                "success": True,
                "output": (
                    f"▶ Now working on: {updated[0]}"
                    if len(updated) == 1
                    else f"Updated {len(updated)} todos"
                ),
                "updated_count": len(updated),
            }
        return {
            "success": True,
            "output": "No changes needed",
            "updated_count": 0,
        }

    def get_active_todo_message(self) -> Optional[str]:
        """Get the activeForm text of the current in_progress todo.

        Returns:
            The active_form string if there's a todo in "doing" status with active_form set,
            otherwise None.
        """
        for todo in self._todos.values():
            if todo.status == "doing" and todo.active_form:
                return todo.active_form
        return None

    def has_todos(self) -> bool:
        """Check if any todos exist.

        Returns:
            True if any todos have been created, False otherwise.
        """
        return bool(self._todos)

    def has_incomplete_todos(self) -> bool:
        """Check if any todos remain incomplete.

        Returns:
            True if any todo has status != 'done', False otherwise.
        """
        return any(t.status != "done" for t in self._todos.values())

    def get_incomplete_todos(self) -> List["TodoItem"]:
        """Get all todos that are not done.

        Returns:
            List of TodoItem objects with status != 'done'.
        """
        return [t for t in self._todos.values() if t.status != "done"]
