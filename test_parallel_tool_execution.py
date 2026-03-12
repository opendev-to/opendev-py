"""Tests for parallel tool execution in the run_loop subagent path."""

import json
import threading
import time
from unittest.mock import MagicMock

from opendev.core.agents.main_agent.run_loop import PARALLELIZABLE_TOOLS, RunLoopMixin
from opendev.repl.react_executor.executor import ReactExecutor


def _make_tool_call(tool_name: str, args: dict, call_id: str) -> dict:
    return {
        "id": call_id,
        "function": {
            "name": tool_name,
            "arguments": json.dumps(args),
        },
    }


class TestFormatToolResult:
    def test_success_result(self):
        result = {"success": True, "output": "file contents here"}
        assert RunLoopMixin._format_tool_result("read_file", result) == "file contents here"

    def test_success_with_separate_response(self):
        result = {"success": True, "output": "raw", "separate_response": "formatted"}
        assert RunLoopMixin._format_tool_result("read_file", result) == "formatted"

    def test_success_with_completion_status(self):
        result = {"success": True, "output": "done", "completion_status": "success"}
        formatted = RunLoopMixin._format_tool_result("spawn_subagent", result)
        assert formatted.startswith("[completion_status=success]")
        assert "done" in formatted

    def test_error_result(self):
        result = {"success": False, "error": "file not found"}
        formatted = RunLoopMixin._format_tool_result("read_file", result)
        assert "Error in read_file" in formatted
        assert "file not found" in formatted

    def test_llm_suffix_appended(self):
        result = {"success": True, "output": "data", "_llm_suffix": "\n[hint: retry]"}
        formatted = RunLoopMixin._format_tool_result("read_file", result)
        assert formatted == "data\n[hint: retry]"


class TestParallelToolDetection:
    """Test that the parallel path is correctly detected."""

    def test_parallelizable_tools_constant_matches_executor(self):
        """PARALLELIZABLE_TOOLS should match the ReactExecutor's set exactly."""
        assert PARALLELIZABLE_TOOLS == ReactExecutor.PARALLELIZABLE_TOOLS

    def test_parallelizable_tools_excludes_mutable(self):
        """Mutable tools should NOT be in the set."""
        assert "bash" not in PARALLELIZABLE_TOOLS
        assert "write_file" not in PARALLELIZABLE_TOOLS
        assert "edit_file" not in PARALLELIZABLE_TOOLS
        assert "task_complete" not in PARALLELIZABLE_TOOLS


class TestExecuteToolsParallel:
    """Test the _execute_tools_parallel method."""

    def _make_mixin(self):
        mixin = RunLoopMixin()
        mixin.tool_registry = MagicMock()
        return mixin

    def _make_deps(self):
        deps = MagicMock()
        deps.mode_manager = MagicMock()
        deps.approval_manager = MagicMock()
        deps.undo_manager = MagicMock()
        return deps

    def test_parallel_execution_returns_all_results(self):
        mixin = self._make_mixin()
        deps = self._make_deps()

        mixin.tool_registry.execute_tool.side_effect = [
            {"success": True, "output": "contents of a.py"},
            {"success": True, "output": "contents of b.py"},
        ]

        tool_calls = [
            _make_tool_call("read_file", {"path": "a.py"}, "call_1"),
            _make_tool_call("read_file", {"path": "b.py"}, "call_2"),
        ]

        results = mixin._execute_tools_parallel(
            tool_calls, deps, task_monitor=None, ui_callback=None, is_subagent=True
        )

        assert len(results) == 2
        assert results["call_1"]["success"] is True
        assert results["call_2"]["success"] is True
        assert mixin.tool_registry.execute_tool.call_count == 2

    def test_parallel_execution_actually_concurrent(self):
        """Verify tools run concurrently using a threading barrier."""
        mixin = self._make_mixin()
        deps = self._make_deps()

        barrier = threading.Barrier(3, timeout=5)  # 3 threads must arrive
        call_times = {}

        def slow_tool(name, args, **kwargs):
            barrier.wait()  # All threads must reach here before any proceeds
            call_times[name] = time.monotonic()
            return {"success": True, "output": f"result for {name}"}

        mixin.tool_registry.execute_tool.side_effect = slow_tool

        tool_calls = [
            _make_tool_call("read_file", {"path": "a.py"}, "c1"),
            _make_tool_call("search", {"query": "foo"}, "c2"),
            _make_tool_call("list_files", {"path": "."}, "c3"),
        ]

        results = mixin._execute_tools_parallel(
            tool_calls, deps, task_monitor=None, ui_callback=None, is_subagent=True
        )

        # If execution were sequential, the barrier would timeout
        assert len(results) == 3
        assert all(r["success"] for r in results.values())

    def test_parallel_handles_exception_in_one_tool(self):
        mixin = self._make_mixin()
        deps = self._make_deps()

        def side_effect(name, args, **kwargs):
            if name == "search":
                raise RuntimeError("search index corrupt")
            return {"success": True, "output": "ok"}

        mixin.tool_registry.execute_tool.side_effect = side_effect

        tool_calls = [
            _make_tool_call("read_file", {"path": "a.py"}, "c1"),
            _make_tool_call("search", {"query": "foo"}, "c2"),
        ]

        results = mixin._execute_tools_parallel(
            tool_calls, deps, task_monitor=None, ui_callback=None, is_subagent=False
        )

        assert results["c1"]["success"] is True
        assert results["c2"]["success"] is False
        assert "search index corrupt" in results["c2"]["error"]

    def test_parallel_respects_interrupt(self):
        mixin = self._make_mixin()
        deps = self._make_deps()

        monitor = MagicMock()
        monitor.should_interrupt.return_value = True

        tool_calls = [
            _make_tool_call("read_file", {"path": "a.py"}, "c1"),
            _make_tool_call("read_file", {"path": "b.py"}, "c2"),
        ]

        results = mixin._execute_tools_parallel(
            tool_calls, deps, task_monitor=monitor, ui_callback=None, is_subagent=False
        )

        # Should not have called execute_tool at all
        assert mixin.tool_registry.execute_tool.call_count == 0
        assert all(r.get("interrupted") for r in results.values())
