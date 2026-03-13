"""CRUD operations for todo items."""

import logging
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from opendev.core.context_engineering.tools.handlers.todo_handler.models import TodoItem

logger = logging.getLogger(__name__)


class CrudMixin:
    """Mixin providing create/find/update/complete operations."""

    def create_todo(
        self,
        title: str,
        status: str = "todo",
        active_form: str = "",
        log: str = "",
        expanded: bool = False,
    ) -> dict:
        """Create a new todo item.

        Args:
            title: Todo title/description
            status: Status ("todo", "doing", "done" OR "pending", "in_progress", "completed")
            active_form: Present continuous form for spinner display (e.g., "Running tests")
            log: Optional log/notes
            expanded: Whether to show expanded in UI

        Returns:
            Result dict with success status and todo ID
        """
        from opendev.core.context_engineering.tools.handlers.todo_handler.models import TodoItem

        # Map Deep Agent statuses to internal statuses
        status_map = {
            "pending": "todo",
            "in_progress": "doing",
            "completed": "done",
        }

        # Normalize status
        normalized_status = status_map.get(status, status)

        # Validate status
        if normalized_status not in ["todo", "doing", "done"]:
            return {
                "success": False,
                "error": f"Invalid status '{status}'. Must be 'todo', 'doing', or 'done' (or 'pending', 'in_progress', 'completed').",
                "output": None,
            }

        # Strip markdown formatting from title and active_form
        title = self._strip_markdown(title)
        if active_form:
            active_form = self._strip_markdown(active_form)

        # Create todo with Deep Agent compatible ID format
        todo_id = f"todo-{self._next_id}"
        self._next_id += 1

        todo = TodoItem(
            id=todo_id,
            title=title,
            status=normalized_status,
            active_form=active_form,
            log=log,
            expanded=expanded,
        )

        self._todos[todo_id] = todo
        logger.debug(f"[TODO] Created: {todo_id} = {title[:40]}...")

        return {
            "success": True,
            "output": f"Created todo #{todo_id}: {title}",
            "todo_id": todo_id,
            "todo": asdict(todo),
        }

    def _find_todo(self, id: str | int) -> tuple[Optional[str], Optional["TodoItem"]]:
        """Find a todo by ID, trying multiple matching strategies.

        Supports both 1-based indexing (Claude's default) and 0-based indexing.
        Also supports finding by title string, kebab-case slugs, and fuzzy matching.

        Args:
            id: Todo ID in formats: 1, "1", "todo-1", exact title, kebab-case slug

        Returns:
            Tuple of (actual_id, todo_item) or (None, None) if not found
        """
        # Convert to string first (handle both int and str inputs)
        id = str(id)

        # Empty string should return None
        if not id or not id.strip():
            return None, None

        # Try exact match first (no warning needed)
        if id in self._todos:
            return id, self._todos[id]

        # If numeric ID provided, try both 0-based and 1-based indexing
        if id.isdigit():
            numeric_id = int(id)

            # Try 0-based indexing first (Deep Agent format): "0" -> "todo-1", "2" -> "todo-3"
            one_based_id = numeric_id + 1
            todo_id = f"todo-{one_based_id}"
            if todo_id in self._todos:
                return todo_id, self._todos[todo_id]

            # Fallback to 1-based indexing (Claude uses 1-based): "1" -> "todo-1"
            todo_id = f"todo-{numeric_id}"
            if todo_id in self._todos:
                return todo_id, self._todos[todo_id]

        # If "todo-X" provided, try numeric format
        if id.startswith("todo-"):
            numeric_id = id[5:]
            if numeric_id in self._todos:
                return numeric_id, self._todos[numeric_id]

        # If ":X" provided (colon format), treat as numeric 0-based index
        if id.startswith(":") and len(id) > 1:
            numeric_part = id[1:]
            if numeric_part.isdigit():
                # Convert ":1" -> "todo-2" (0-based to 1-based)
                one_based_id = int(numeric_part) + 1
                todo_id = f"todo-{one_based_id}"
                if todo_id in self._todos:
                    return todo_id, self._todos[todo_id]

        # If "todo_X" provided (Deep Agent format with underscore), convert to "todo-X"
        if id.startswith("todo_"):
            numeric_part = id[5:]
            if numeric_part.isdigit():
                # Convert "todo_1" -> "todo-1" (our internal format)
                internal_id = f"todo-{numeric_part}"
                if internal_id in self._todos:
                    return internal_id, self._todos[internal_id]

        # Try to find by title (case-sensitive exact match)
        for todo_id, todo in self._todos.items():
            if todo.title == id:
                return todo_id, todo

        # Try case-insensitive exact match
        id_lower = id.lower()
        for todo_id, todo in self._todos.items():
            if todo.title.lower() == id_lower:
                return todo_id, todo

        # Try kebab-case slug matching (e.g., "implement-basic-level" -> "Implement basic level design...")
        # Convert kebab-case to words and try fuzzy matching
        if "-" in id:
            # Convert "implement-basic-level" -> "implement basic level"
            slug_words = id.replace("-", " ").lower()
            for todo_id, todo in self._todos.items():
                title_lower = todo.title.lower()
                # Check if slug words appear at start of title
                if title_lower.startswith(slug_words):
                    return todo_id, todo
                # Check if all slug words appear in title (in order)
                if all(word in title_lower for word in slug_words.split()):
                    # Verify words appear in order
                    pos = 0
                    all_in_order = True
                    for word in slug_words.split():
                        idx = title_lower.find(word, pos)
                        if idx == -1:
                            all_in_order = False
                            break
                        pos = idx + len(word)
                    if all_in_order:
                        return todo_id, todo

        # Try partial matching - if id is contained in title
        for todo_id, todo in self._todos.items():
            if id_lower in todo.title.lower():
                return todo_id, todo

        return None, None

    def update_todo(
        self,
        id: str,
        title: Optional[str] = None,
        status: Optional[str] = None,
        active_form: Optional[str] = None,
        log: Optional[str] = None,
        expanded: Optional[bool] = None,
    ) -> dict:
        """Update an existing todo item.

        Args:
            id: Todo ID
            title: New title (optional)
            status: New status ("todo", "doing", "done" OR "pending", "in_progress", "completed") (optional)
            active_form: Present continuous form for spinner display (optional)
            log: New log/notes (optional)
            expanded: New expanded state (optional)

        Returns:
            Result dict with success status
        """
        logger.debug(f"[TODO] update_todo called: id={id}, status={status}")
        actual_id, todo = self._find_todo(id)
        if todo is None:
            logger.debug(f"[TODO] Todo not found: id={id}")
            # Build helpful error message with valid ID suggestions
            valid_ids = sorted(self._todos.keys())
            if valid_ids:
                ids_list = ", ".join(valid_ids)
                error_msg = (
                    f"Todo '{id}' not found. "
                    f"Valid IDs: {ids_list}. "
                    f"Use exact 'todo-N' format for best results."
                )
            else:
                error_msg = f"Todo '{id}' not found. No todos exist yet. Create todos with write_todos first."

            return {
                "success": False,
                "error": error_msg,
                "output": None,
            }

        logger.debug(f"[TODO] Found todo: actual_id={actual_id}, title={todo.title[:30]}...")
        old_status = todo.status

        # Update fields
        if title is not None:
            todo.title = self._strip_markdown(title)
        if status is not None:
            # Map Deep Agent statuses to internal statuses
            status_map = {
                "pending": "todo",
                "in_progress": "doing",
                "completed": "done",
            }

            # Normalize status
            normalized_status = status_map.get(status, status)

            if normalized_status not in ["todo", "doing", "done"]:
                return {
                    "success": False,
                    "error": f"Invalid status '{status}'. Must be 'todo', 'doing', or 'done' (or 'pending', 'in_progress', 'completed').",
                    "output": None,
                }
            todo.status = normalized_status

            # ENFORCEMENT: Ensure only one todo can be "doing" at a time
            if normalized_status == "doing":
                for other_id, other_todo in self._todos.items():
                    if other_id != actual_id and other_todo.status == "doing":
                        other_todo.status = "todo"

        if active_form is not None:
            todo.active_form = self._strip_markdown(active_form)
        if log is not None:
            todo.log = log
        if expanded is not None:
            todo.expanded = expanded

        todo.updated_at = datetime.now().isoformat()
        logger.debug(f"[TODO] Status changed: {old_status} -> {todo.status}")

        # Generate minimal status update
        if todo.status == "doing":
            output_lines = [f"▶ Now working on: {todo.title}"]
        elif todo.status == "done":
            output_lines = [f"Completed: {todo.title}"]
        else:
            output_lines = [f"⏸ Paused: {todo.title}"]

        return {
            "success": True,
            "output": "\n".join(output_lines),
            "todo": asdict(todo),
        }

    def complete_todo(self, id: str, log: Optional[str] = None) -> dict:
        """Mark a todo as complete.

        Args:
            id: Todo ID
            log: Optional final log entry

        Returns:
            Result dict with success status
        """
        logger.debug(f"[TODO] complete_todo called: id={id}")
        actual_id, todo = self._find_todo(id)
        if todo is None:
            # Build helpful error message with valid ID suggestions
            valid_ids = sorted(self._todos.keys())
            if valid_ids:
                ids_list = ", ".join(valid_ids)
                error_msg = (
                    f"Todo '{id}' not found. "
                    f"Valid IDs: {ids_list}. "
                    f"Use exact 'todo-N' format for best results."
                )
            else:
                error_msg = f"Todo '{id}' not found. No todos exist yet. Create todos with write_todos first."

            return {
                "success": False,
                "error": error_msg,
                "output": None,
            }
        old_status = todo.status
        todo.status = "done"
        logger.debug(
            f"[TODO] Completed: actual_id={actual_id}, status changed: {old_status} -> done"
        )

        if log:
            if todo.log:
                todo.log += f"\n{log}"
            else:
                todo.log = log

        todo.updated_at = datetime.now().isoformat()

        # Generate minimal completion output
        output_lines = [f"Completed: {todo.title}"]

        return {
            "success": True,
            "output": "\n".join(output_lines),
            "todo": asdict(todo),
        }

    def complete_and_activate_next(self, id: str, log: Optional[str] = None) -> dict:
        """Complete a todo and automatically activate the next pending one.

        This is an atomic operation that:
        1. Marks the specified todo as completed
        2. Deactivates any other active todos
        3. Activates the next pending todo (if any)

        Args:
            id: Todo ID to complete
            log: Optional completion log message

        Returns:
            Result dict with success status and formatted output
        """
        actual_id, todo = self._find_todo(id)
        if not todo:
            return {
                "success": False,
                "error": f"Todo #{id} not found",
                "output": None,
            }

        # Mark current todo as completed
        todo.status = "done"
        if log is not None:
            todo.log = log
        todo.updated_at = datetime.now().isoformat()

        # Find the next pending todo to activate
        next_todo = None
        pending_todos = [t for t in self._todos.values() if t.status == "todo"]

        if pending_todos:
            # Sort by original creation order
            def extract_id_number(todo_id: str) -> int:
                if todo_id.startswith("todo-"):
                    return int(todo_id[5:])
                return int(todo_id)

            next_todo = min(pending_todos, key=lambda t: extract_id_number(t.id))
            next_todo.status = "doing"

        # Generate output
        output_lines = [f"Completed: {todo.title}"]
        if next_todo:
            output_lines.append(f"▶ Now working on: {next_todo.title}")
        else:
            output_lines.append("All todos completed!")

        return {
            "success": True,
            "output": "\n".join(output_lines),
            "todo": asdict(todo),
        }
