"""Tests for doom-loop detection auto-recovery (no user prompt)."""

from unittest.mock import MagicMock

import pytest

from opendev.repl.react_executor.executor import IterationContext, LoopAction, ReactExecutor


def _make_tool_call(name: str, arguments: str, call_id: str = "call_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _make_ctx(**overrides) -> IterationContext:
    """Build a minimal IterationContext with sensible defaults."""
    defaults = dict(
        query="test",
        messages=[{"role": "system", "content": "sys"}],
        agent=MagicMock(),
        tool_registry=MagicMock(),
        approval_manager=MagicMock(),
        undo_manager=MagicMock(),
        ui_callback=None,
    )
    defaults.update(overrides)
    return IterationContext(**defaults)


class TestDetectDoomLoop:
    """Unit tests for _detect_doom_loop fingerprinting."""

    def test_no_doom_loop_under_threshold(self):
        """2 identical calls don't trigger (under threshold of 3)."""
        executor = ReactExecutor.__new__(ReactExecutor)
        ctx = _make_ctx()
        tc = _make_tool_call("read_file", '{"path": "/foo.py"}')

        # First call
        result = executor._detect_doom_loop([tc], ctx)
        assert result is None

        # Second call
        result = executor._detect_doom_loop([tc], ctx)
        assert result is None

    def test_doom_loop_at_threshold(self):
        """3 identical calls trigger detection."""
        executor = ReactExecutor.__new__(ReactExecutor)
        ctx = _make_ctx()
        tc = _make_tool_call("read_file", '{"path": "/foo.py"}')

        executor._detect_doom_loop([tc], ctx)
        executor._detect_doom_loop([tc], ctx)
        result = executor._detect_doom_loop([tc], ctx)

        assert result is not None
        assert "read_file" in result
        assert "3 times consecutively" in result

    def test_different_tool_calls_no_trigger(self):
        """Varied fingerprints in window don't hit threshold."""
        executor = ReactExecutor.__new__(ReactExecutor)
        ctx = _make_ctx()

        for i in range(10):
            tc = _make_tool_call("read_file", f'{{"path": "/file{i}.py"}}')
            result = executor._detect_doom_loop([tc], ctx)

        assert result is None

    def test_mixed_calls_with_one_repeating_no_trigger(self):
        """Repeating fingerprint interleaved with different work does NOT trigger."""
        executor = ReactExecutor.__new__(ReactExecutor)
        ctx = _make_ctx()

        repeated = _make_tool_call("run_command", '{"command": "ls"}')
        different = _make_tool_call("read_file", '{"path": "/a.py"}')

        executor._detect_doom_loop([repeated], ctx)
        executor._detect_doom_loop([different], ctx)
        executor._detect_doom_loop([repeated], ctx)
        executor._detect_doom_loop(
            [different, _make_tool_call("read_file", '{"path": "/b.py"}')], ctx
        )
        result = executor._detect_doom_loop([repeated], ctx)

        assert result is None

    def test_two_step_cycle_triggers(self):
        """[A, B, A, B, A, B] triggers as a 2-step cycle."""
        executor = ReactExecutor.__new__(ReactExecutor)
        ctx = _make_ctx()

        a = _make_tool_call("run_command", '{"command": "npm test"}')
        b = _make_tool_call("read_file", '{"path": "/foo.py"}')

        for _ in range(2):
            executor._detect_doom_loop([a], ctx)
            executor._detect_doom_loop([b], ctx)

        executor._detect_doom_loop([a], ctx)
        result = executor._detect_doom_loop([b], ctx)

        assert result is not None
        assert "2-step cycle" in result

    def test_three_step_cycle_triggers(self):
        """[A, B, C, A, B, C, A, B, C] triggers as a 3-step cycle."""
        executor = ReactExecutor.__new__(ReactExecutor)
        ctx = _make_ctx()

        a = _make_tool_call("run_command", '{"command": "npm test"}')
        b = _make_tool_call("read_file", '{"path": "/foo.py"}')
        c = _make_tool_call("write_file", '{"path": "/bar.py", "content": "x"}')

        for _ in range(2):
            executor._detect_doom_loop([a], ctx)
            executor._detect_doom_loop([b], ctx)
            executor._detect_doom_loop([c], ctx)

        executor._detect_doom_loop([a], ctx)
        executor._detect_doom_loop([b], ctx)
        result = executor._detect_doom_loop([c], ctx)

        assert result is not None
        assert "3-step cycle" in result

    def test_edit_test_interleaving_no_trigger(self):
        """edit:a, test:x, edit:b, test:x, edit:c, test:x -> no trigger (edits differ)."""
        executor = ReactExecutor.__new__(ReactExecutor)
        ctx = _make_ctx()

        test = _make_tool_call("run_command", '{"command": "npm test"}')

        for i in range(3):
            edit = _make_tool_call("write_file", f'{{"path": "/file{i}.py", "content": "v{i}"}}')
            executor._detect_doom_loop([edit], ctx)
            result = executor._detect_doom_loop([test], ctx)

        assert result is None

    def test_partial_cycle_no_trigger(self):
        """[A, B, A, B] (only 2 reps of a 2-step cycle) -> no trigger."""
        executor = ReactExecutor.__new__(ReactExecutor)
        ctx = _make_ctx()

        a = _make_tool_call("run_command", '{"command": "npm test"}')
        b = _make_tool_call("read_file", '{"path": "/foo.py"}')

        executor._detect_doom_loop([a], ctx)
        executor._detect_doom_loop([b], ctx)
        executor._detect_doom_loop([a], ctx)
        result = executor._detect_doom_loop([b], ctx)

        assert result is None

    def test_cycle_broken_by_different_call(self):
        """[A, B, A, B, C, A, B] -> no trigger (cycle broken by C)."""
        executor = ReactExecutor.__new__(ReactExecutor)
        ctx = _make_ctx()

        a = _make_tool_call("run_command", '{"command": "npm test"}')
        b = _make_tool_call("read_file", '{"path": "/foo.py"}')
        c = _make_tool_call("search", '{"query": "hello"}')

        executor._detect_doom_loop([a], ctx)
        executor._detect_doom_loop([b], ctx)
        executor._detect_doom_loop([a], ctx)
        executor._detect_doom_loop([b], ctx)
        executor._detect_doom_loop([c], ctx)
        executor._detect_doom_loop([a], ctx)
        result = executor._detect_doom_loop([b], ctx)

        assert result is None


class TestDoomLoopAutoRecovery:
    """Integration tests for the escalating nudge flow in _process_tool_calls."""

    @pytest.fixture
    def executor(self):
        """Build a ReactExecutor with mocked internals for tool processing."""
        ex = ReactExecutor.__new__(ReactExecutor)
        ex._active_interrupt_token = None
        ex._injection_queue = MagicMock()
        ex._injection_queue.empty.return_value = True
        ex.session_manager = MagicMock()
        ex.config = MagicMock()
        ex.console = None
        ex._last_operation_summary = None
        ex._compactor = None
        ex._snapshot_manager = None
        ex._parallel_executor = None
        ex._tool_executor = None
        ex._cost_tracker = None
        ex.READ_OPERATIONS = ReactExecutor.READ_OPERATIONS
        ex.PARALLELIZABLE_TOOLS = ReactExecutor.PARALLELIZABLE_TOOLS
        ex.MAX_NUDGE_ATTEMPTS = ReactExecutor.MAX_NUDGE_ATTEMPTS
        ex.MAX_TODO_NUDGES = ReactExecutor.MAX_TODO_NUDGES
        ex.DOOM_LOOP_THRESHOLD = ReactExecutor.DOOM_LOOP_THRESHOLD
        ex.OFFLOAD_THRESHOLD = ReactExecutor.OFFLOAD_THRESHOLD
        ex._mode_manager = MagicMock()
        return ex

    def _fill_doom_loop(self, executor, ctx, tc, count=3):
        """Push identical tool calls into the deque to trigger detection."""
        for _ in range(count):
            fp = executor._tool_call_fingerprint(
                tc["function"]["name"], tc["function"]["arguments"]
            )
            ctx.recent_tool_calls.append(fp)

    def test_first_nudge_returns_continue(self, executor):
        """First doom-loop detection injects guidance and returns CONTINUE."""
        ctx = _make_ctx()
        tc = _make_tool_call("run_command", '{"command": "ls"}', call_id="c1")

        # Pre-fill deque so the next _detect_doom_loop triggers
        self._fill_doom_loop(executor, ctx, tc, count=2)

        result = executor._process_tool_calls(ctx, [tc], "", None)

        assert result == LoopAction.CONTINUE
        assert ctx.doom_loop_nudge_count == 1
        # Guidance message injected
        assert any("[SYSTEM WARNING]" in m.get("content", "") for m in ctx.messages)
        # Deque cleared for fresh window
        assert len(ctx.recent_tool_calls) == 0

    def test_second_nudge_notifies_user(self, executor):
        """Second detection notifies user via on_message and returns CONTINUE."""
        ui_callback = MagicMock()
        ctx = _make_ctx(ui_callback=ui_callback)
        ctx.doom_loop_nudge_count = 1  # Already nudged once
        tc = _make_tool_call("run_command", '{"command": "ls"}', call_id="c2")

        self._fill_doom_loop(executor, ctx, tc, count=2)

        result = executor._process_tool_calls(ctx, [tc], "", None)

        assert result == LoopAction.CONTINUE
        assert ctx.doom_loop_nudge_count == 2
        ui_callback.on_message.assert_called_once()
        assert "stuck" in ui_callback.on_message.call_args[0][0].lower()

    def test_third_strike_force_stops(self, executor):
        """Third detection returns BREAK and notifies user."""
        ui_callback = MagicMock()
        ctx = _make_ctx(ui_callback=ui_callback)
        ctx.doom_loop_nudge_count = 2  # Already nudged twice
        tc = _make_tool_call("run_command", '{"command": "ls"}', call_id="c3")

        self._fill_doom_loop(executor, ctx, tc, count=2)

        result = executor._process_tool_calls(ctx, [tc], "", None)

        assert result == LoopAction.BREAK
        assert ctx.doom_loop_nudge_count == 3
        ui_callback.on_message.assert_called_once()
        assert "stopping" in ui_callback.on_message.call_args[0][0].lower()
        # Final system message injected
        assert any("STOP and explain" in m.get("content", "") for m in ctx.messages)

    def test_deque_cleared_after_nudge(self, executor):
        """Confirm recent_tool_calls is empty after each nudge."""
        ctx = _make_ctx()
        tc = _make_tool_call("run_command", '{"command": "ls"}', call_id="c4")

        self._fill_doom_loop(executor, ctx, tc, count=2)
        executor._process_tool_calls(ctx, [tc], "", None)

        assert len(ctx.recent_tool_calls) == 0

    def test_no_approval_prompt_used(self, executor):
        """Verify the approval manager is never called for doom-loop detection."""
        ctx = _make_ctx()
        tc = _make_tool_call("run_command", '{"command": "ls"}', call_id="c5")

        self._fill_doom_loop(executor, ctx, tc, count=2)
        executor._process_tool_calls(ctx, [tc], "", None)

        # approval_manager.request_approval should NOT be called
        ctx.approval_manager.request_approval.assert_not_called()
