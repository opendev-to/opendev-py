"""Tests for BridgeUICallback dual-forwarding behavior."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from opendev.ui_textual.bridge_callback import BridgeUICallback


class TestBridgeUICallbackForwarding:
    """Verify both TUI and web callbacks are called, and web errors don't propagate."""

    def _make_pair(self):
        tui = MagicMock()
        web = MagicMock()
        return tui, web, BridgeUICallback(tui, web)

    def test_on_thinking_start_forwards_both(self):
        tui, web, bridge = self._make_pair()
        bridge.on_thinking_start()
        tui.on_thinking_start.assert_called_once()
        web.on_thinking_start.assert_called_once()

    def test_on_thinking_complete_forwards_both(self):
        tui, web, bridge = self._make_pair()
        bridge.on_thinking_complete()
        tui.on_thinking_complete.assert_called_once()
        web.on_thinking_complete.assert_called_once()

    def test_on_assistant_message_forwards_both(self):
        tui, web, bridge = self._make_pair()
        bridge.on_assistant_message("hello")
        tui.on_assistant_message.assert_called_once_with("hello")
        web.on_assistant_message.assert_called_once_with("hello")

    def test_on_progress_start_forwards_both(self):
        tui, web, bridge = self._make_pair()
        bridge.on_progress_start("loading")
        tui.on_progress_start.assert_called_once_with("loading")
        web.on_progress_start.assert_called_once_with("loading")

    def test_on_progress_complete_forwards_both(self):
        tui, web, bridge = self._make_pair()
        bridge.on_progress_complete("done", success=True)
        tui.on_progress_complete.assert_called_once_with("done", success=True)
        web.on_progress_complete.assert_called_once_with("done", success=True)

    def test_on_cost_update_forwards_both(self):
        tui, web, bridge = self._make_pair()
        bridge.on_cost_update(1.23)
        tui.on_cost_update.assert_called_once_with(1.23)
        web.on_cost_update.assert_called_once_with(1.23)

    def test_on_context_usage_forwards_both(self):
        tui, web, bridge = self._make_pair()
        bridge.on_context_usage(42.5)
        tui.on_context_usage.assert_called_once_with(42.5)
        web.on_context_usage.assert_called_once_with(42.5)

    def test_on_single_agent_start_forwards_both(self):
        tui, web, bridge = self._make_pair()
        bridge.on_single_agent_start("explorer", "search files", "tc_1")
        tui.on_single_agent_start.assert_called_once_with("explorer", "search files", "tc_1")
        web.on_single_agent_start.assert_called_once_with("explorer", "search files", "tc_1")

    def test_on_parallel_agents_done_forwards_both(self):
        tui, web, bridge = self._make_pair()
        bridge.on_parallel_agents_done()
        tui.on_parallel_agents_done.assert_called_once()
        web.on_parallel_agents_done.assert_called_once()


class TestBridgeWebErrorIsolation:
    """Web callback errors must never propagate to TUI."""

    def test_web_error_on_thinking_start_suppressed(self):
        tui = MagicMock()
        web = MagicMock()
        web.on_thinking_start.side_effect = RuntimeError("ws disconnected")
        bridge = BridgeUICallback(tui, web)
        # Should not raise
        bridge.on_thinking_start()
        tui.on_thinking_start.assert_called_once()

    def test_web_error_on_assistant_message_suppressed(self):
        tui = MagicMock()
        web = MagicMock()
        web.on_assistant_message.side_effect = ConnectionError("broken pipe")
        bridge = BridgeUICallback(tui, web)
        bridge.on_assistant_message("test")
        tui.on_assistant_message.assert_called_once_with("test")

    def test_web_error_on_tool_call_suppressed(self):
        tui = MagicMock()
        web = MagicMock()
        web.on_tool_call.side_effect = Exception("boom")
        bridge = BridgeUICallback(tui, web)
        bridge.on_tool_call("bash", {"command": "ls"}, tool_call_id="tc_1")
        tui.on_tool_call.assert_called_once()


class TestBridgeNoWebCallback:
    """When web_callback is None, TUI still works normally."""

    def test_tui_only(self):
        tui = MagicMock()
        bridge = BridgeUICallback(tui, None)
        bridge.on_thinking_start()
        bridge.on_assistant_message("hello")
        bridge.on_cost_update(0.5)
        tui.on_thinking_start.assert_called_once()
        tui.on_assistant_message.assert_called_once_with("hello")
        tui.on_cost_update.assert_called_once_with(0.5)


class TestBridgePlanApproval:
    """Plan approval delegates to TUI only."""

    def test_set_plan_approval_callback_delegates_to_tui(self):
        tui = MagicMock()
        web = MagicMock()
        bridge = BridgeUICallback(tui, web)
        cb = MagicMock()
        bridge.set_plan_approval_callback(cb)
        tui.set_plan_approval_callback.assert_called_once_with(cb)

    def test_request_plan_approval_uses_tui_result(self):
        tui = MagicMock()
        tui.request_plan_approval.return_value = {"action": "approve", "feedback": ""}
        web = MagicMock()
        bridge = BridgeUICallback(tui, web)
        result = bridge.request_plan_approval("plan text")
        assert result == {"action": "approve", "feedback": ""}
        tui.request_plan_approval.assert_called_once()


class TestBridgeNestedCalls:
    """Nested calls are collected from TUI callback."""

    def test_get_and_clear_nested_calls_from_tui(self):
        tui = MagicMock()
        tui.get_and_clear_nested_calls.return_value = ["call1", "call2"]
        web = MagicMock()
        web.get_and_clear_nested_calls.return_value = ["web_call"]
        bridge = BridgeUICallback(tui, web)
        result = bridge.get_and_clear_nested_calls()
        assert result == ["call1", "call2"]
        # Web is also drained
        web.get_and_clear_nested_calls.assert_called_once()


class TestBridgeModeState:
    """Test bridge mode detection on WebState."""

    def test_is_bridge_mode_false_by_default(self):
        from opendev.web.state import WebState

        state = WebState.__new__(WebState)
        state.tui_message_injector = None
        assert state.is_bridge_mode is False

    def test_is_bridge_mode_true_when_injector_set(self):
        from opendev.web.state import WebState

        state = WebState.__new__(WebState)
        state.tui_message_injector = lambda msg, sid: None
        assert state.is_bridge_mode is True
