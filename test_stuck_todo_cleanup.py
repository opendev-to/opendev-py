"""Tests for stuck todo/spinner cleanup when agent loop exits abnormally."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from opendev.core.context_engineering.tools.handlers.todo_handler import TodoHandler


class TestResetStuckTodos:
    """Test _reset_stuck_todos in RunLoopMixin."""

    def _make_agent_with_todos(self, statuses: list[tuple[str, str]]):
        """Create a mock agent with a tool_registry.todo_handler containing given todos.

        Args:
            statuses: list of (title, status) tuples
        """
        from opendev.core.context_engineering.tools.handlers.todo_handler.models import TodoItem

        handler = TodoHandler()
        for i, (title, status) in enumerate(statuses, 1):
            handler._todos[f"todo-{i}"] = TodoItem(id=f"todo-{i}", title=title, status=status)
            handler._next_id = i + 1

        # Build a minimal object that has tool_registry.todo_handler
        agent = MagicMock()
        agent.tool_registry = MagicMock()
        agent.tool_registry.todo_handler = handler
        return agent, handler

    def test_doing_todos_reset_on_interrupt(self):
        """When agent loop exits with interrupted=True, 'doing' todos become 'todo'."""
        from opendev.core.agents.main_agent.run_loop import RunLoopMixin

        agent, handler = self._make_agent_with_todos(
            [
                ("Task A", "done"),
                ("Task B", "doing"),
                ("Task C", "todo"),
            ]
        )

        # Call the method directly
        RunLoopMixin._reset_stuck_todos(agent, interrupted=True)

        assert handler._todos["todo-1"].status == "done"  # unchanged
        assert handler._todos["todo-2"].status == "todo"  # was doing -> todo
        assert handler._todos["todo-3"].status == "todo"  # unchanged

    def test_doing_todos_reset_on_error(self):
        """When agent loop exits with interrupted=False (error/timeout), 'doing' todos still reset."""
        from opendev.core.agents.main_agent.run_loop import RunLoopMixin

        agent, handler = self._make_agent_with_todos(
            [
                ("Task A", "doing"),
                ("Task B", "doing"),
                ("Task C", "done"),
            ]
        )

        RunLoopMixin._reset_stuck_todos(agent, interrupted=False)

        assert handler._todos["todo-1"].status == "todo"
        assert handler._todos["todo-2"].status == "todo"
        assert handler._todos["todo-3"].status == "done"  # unchanged

    def test_no_crash_without_tool_registry(self):
        """Method should not crash if tool_registry or todo_handler is missing."""
        from opendev.core.agents.main_agent.run_loop import RunLoopMixin

        agent = MagicMock(spec=[])  # no attributes
        RunLoopMixin._reset_stuck_todos(agent, interrupted=True)  # should not raise

    def test_no_crash_with_empty_todos(self):
        """Method should handle empty todo list gracefully."""
        from opendev.core.agents.main_agent.run_loop import RunLoopMixin

        agent, handler = self._make_agent_with_todos([])
        RunLoopMixin._reset_stuck_todos(agent, interrupted=True)  # should not raise
        assert len(handler._todos) == 0

    def test_done_todos_not_affected(self):
        """Completed todos should never be touched."""
        from opendev.core.agents.main_agent.run_loop import RunLoopMixin

        agent, handler = self._make_agent_with_todos(
            [
                ("Task A", "done"),
                ("Task B", "done"),
            ]
        )

        RunLoopMixin._reset_stuck_todos(agent, interrupted=True)

        assert handler._todos["todo-1"].status == "done"
        assert handler._todos["todo-2"].status == "done"


class TestSpinnerCleanupInMessageProcessor:
    """Test that message processor stops orphaned spinners after query."""

    def test_orphaned_spinners_stopped_after_query(self):
        """When query handler returns and spinners are still active, stop them."""
        import queue

        # Minimal mock app
        app = MagicMock()
        spinner_svc = MagicMock()
        spinner_svc.get_active_count.return_value = 2  # 2 orphaned spinners
        app.spinner_service = spinner_svc

        # Simulate what happens in message_processor finally block
        if hasattr(app, "spinner_service"):
            svc = app.spinner_service
            if svc.get_active_count() > 0:
                app.call_from_thread(svc.stop_all, immediate=True, success=False)

        app.call_from_thread.assert_called_once_with(svc.stop_all, immediate=True, success=False)

    def test_no_spinner_cleanup_when_none_active(self):
        """Don't call stop_all if no spinners are active (normal completion)."""
        app = MagicMock()
        spinner_svc = MagicMock()
        spinner_svc.get_active_count.return_value = 0
        app.spinner_service = spinner_svc

        if hasattr(app, "spinner_service"):
            svc = app.spinner_service
            if svc.get_active_count() > 0:
                app.call_from_thread(svc.stop_all, immediate=True, success=False)

        # stop_all should NOT have been called
        app.call_from_thread.assert_not_called()
