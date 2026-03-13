"""Main TodoHandler class composing CRUD and query mixins."""

import logging
import re
from typing import Dict, List

from opendev.core.context_engineering.tools.handlers.todo_handler.models import TodoItem
from opendev.core.context_engineering.tools.handlers.todo_handler.crud import CrudMixin
from opendev.core.context_engineering.tools.handlers.todo_handler.query import QueryMixin

logger = logging.getLogger(__name__)


class TodoHandler(CrudMixin, QueryMixin):
    """Handler for todo/task management operations."""

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Strip markdown formatting from todo titles."""
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text)
        text = re.sub(r"~~(.+?)~~", r"\1", text)
        text = re.sub(r"^#{1,6}\s+", "", text)
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
        return text.strip()

    def __init__(self):
        """Initialize todo handler with in-memory storage."""
        self._todos: Dict[str, TodoItem] = {}
        self._next_id = 1

    def write_todos(self, todos: List[str] | List[dict]) -> dict:
        """Create multiple todo items in a single call.

        Supports both formats:
        - List[str]: Simple string list ["Task 1", "Task 2"]
        - List[dict]: Deep Agent format [{"content": "Task 1", "status": "pending"}]

        Args:
            todos: List of todo titles/descriptions (str) or todo objects (dict)

        Returns:
            Result dict with success status and summary
        """
        if not todos:
            return {
                "success": False,
                "error": "No todos provided. 'todos' parameter must be a non-empty list.",
                "output": None,
            }

        if not isinstance(todos, list):
            return {
                "success": False,
                "error": f"'todos' must be a list. Got {type(todos).__name__}.",
                "output": None,
            }

        # Normalize to string list
        # Handle both List[str] and List[dict] formats (Deep Agent compatibility)
        normalized_todos = []
        for item in todos:
            if isinstance(item, str):
                normalized_todos.append(item)
            elif isinstance(item, dict):
                # Extract 'content', 'status', and 'activeForm' fields from Deep Agent's todo dict format
                content = item.get("content", "")
                status = item.get("status", "pending")
                active_form = item.get("activeForm", "")
                if content:
                    # Map Deep Agent status to internal status
                    status_mapping = {
                        "pending": "todo",
                        "in_progress": "doing",
                        "completed": "done",
                        "todo": "todo",
                        "doing": "doing",
                        "done": "done",
                    }
                    mapped_status = status_mapping.get(status, "todo")
                    # Store as tuple to preserve status and activeForm information
                    normalized_todos.append((content, mapped_status, active_form))
            else:
                # Skip invalid items
                continue

        if not normalized_todos:
            return {
                "success": False,
                "error": "No valid todos found in the list.",
                "output": None,
            }

        todos = normalized_todos

        # Check if this is a status-only update (same content, different statuses)
        # This avoids duplicate display when AI calls write_todos twice with same list
        if self._todos and self._is_status_only_update(normalized_todos):
            return self._apply_status_updates(normalized_todos)

        # Clear existing todos - write_todos replaces the entire list
        self._todos.clear()
        self._next_id = 1

        # Create all todos
        results = []
        created_count = 0
        failed_count = 0
        created_ids = []

        logger.debug(f"[TODO] write_todos called with {len(normalized_todos)} items")

        for i, todo_item in enumerate(normalized_todos, 1):
            # Handle both string and tuple formats
            if isinstance(todo_item, tuple):
                if len(todo_item) == 3:
                    todo_text, todo_status, todo_active_form = todo_item
                else:
                    todo_text, todo_status = todo_item
                    todo_active_form = ""
            else:
                todo_text = todo_item
                todo_status = "todo"
                todo_active_form = ""

            if not todo_text or not str(todo_text).strip():
                failed_count += 1
                results.append(f"  {i}. [SKIPPED] Empty todo")
                continue

            # Call create_todo for each item with correct status and activeForm
            result = self.create_todo(
                title=str(todo_text).strip(), status=todo_status, active_form=todo_active_form
            )

            if result.get("success"):
                todo_id = result.get("todo_id", "?")
                created_ids.append(todo_id)
                # Format with symbols based on status (no Rich markup - output goes to plain text)
                if todo_status == "done":
                    results.append(f"  ✓ {str(todo_text).strip()}")
                elif todo_status == "doing":
                    results.append(f"  ▶ {str(todo_text).strip()}")
                else:
                    results.append(f"  ○ {str(todo_text).strip()}")
                created_count += 1
            else:
                error = result.get("error", "Unknown error")
                results.append(f"  ✗ {error}")
                failed_count += 1

        # Build summary with instructive message for continuation
        summary_lines = [
            "Todos updated. Now proceed with the next action.",
            "",
            f"Created {created_count} todo(s) from {len(todos)} item(s):",
            "",
        ]
        summary_lines.extend(results)

        if failed_count > 0:
            summary_lines.append(f"\nWarning: {failed_count} todo(s) failed to create.")

        return {
            "success": True,
            "output": "\n".join(summary_lines),
            "created_count": created_count,
            "failed_count": failed_count,
            "todo_ids": created_ids,
        }

    def clear_todos(self) -> dict:
        """Clear all todos, removing the entire todo list."""
        count = len(self._todos)
        self._todos.clear()
        self._next_id = 1
        return {
            "success": True,
            "output": f"Cleared {count} todo(s). Todo list removed.",
        }
