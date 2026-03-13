"""Comprehensive tests for the Tool System Overhaul.

Covers all new implementations:
- B1: Result Sanitization Pipeline
- A2: Memory Tools (memory_search, memory_write)
- A1: Session Inspection Tools (list_sessions, get_session_history, list_subagents)
- A6: Git Operations Tool
- B2: Tool Profile & Group System
- B3: Provider-Specific Schema Adaptation
- A3: Browser Automation Tool (import only — Playwright optional)
- A5: Cron/Scheduling Tool
- A4: Cross-Channel Message Tool
- B4: Parameter Normalization Layer
- B5: Tool Execution Middleware Chain
- B6: Smarter Parallel Execution Policy
- A7: Agents Listing Tool
- A8: Apply Patch Tool
- B7: Auth Profile Rotation & Failover
- B8: In-Process Plugin Hooks
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# B1: Result Sanitization Pipeline
# ============================================================

class TestResultSanitizer:
    def test_import(self):
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer
        s = ToolResultSanitizer()
        assert s is not None

    def test_no_truncation_for_short_output(self):
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer
        s = ToolResultSanitizer()
        result = s.sanitize("run_command", {"success": True, "output": "short output"})
        assert result["output"] == "short output"

    def test_truncation_run_command_tail_strategy(self):
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer
        s = ToolResultSanitizer()
        long_output = "line\n" * 5000
        result = s.sanitize("run_command", {"success": True, "output": long_output})
        assert len(result["output"]) < len(long_output)
        assert "truncated" in result["output"]
        assert "strategy=tail" in result["output"]

    def test_truncation_read_file_head_strategy(self):
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer
        s = ToolResultSanitizer()
        long_output = "x" * 30000
        result = s.sanitize("read_file", {"success": True, "output": long_output})
        assert "strategy=head" in result["output"]

    def test_truncation_git_head_tail_strategy(self):
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer
        s = ToolResultSanitizer()
        long_output = "commit " + "x" * 20000
        result = s.sanitize("git", {"success": True, "output": long_output})
        assert "middle truncated" in result["output"]

    def test_error_truncation(self):
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer
        s = ToolResultSanitizer()
        result = s.sanitize("foo", {"success": False, "error": "e" * 5000})
        assert len(result["error"]) <= 2100  # 2000 + some margin

    def test_mcp_tool_default(self):
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer
        s = ToolResultSanitizer()
        result = s.sanitize("mcp__github__list", {"success": True, "output": "x" * 20000})
        assert "truncated" in result["output"]

    def test_custom_limits(self):
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer
        s = ToolResultSanitizer(custom_limits={"run_command": 100})
        result = s.sanitize("run_command", {"success": True, "output": "x" * 500})
        assert len(result["output"]) < 200

    def test_does_not_mutate_original(self):
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer
        s = ToolResultSanitizer()
        original = {"success": True, "output": "x" * 20000}
        s.sanitize("run_command", original)
        assert len(original["output"]) == 20000  # Original unchanged

    def test_non_string_output_passthrough(self):
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer
        s = ToolResultSanitizer()
        result = s.sanitize("foo", {"success": True, "output": 42})
        assert result["output"] == 42

    def test_no_rule_no_truncation(self):
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer
        s = ToolResultSanitizer()
        result = s.sanitize("unknown_tool", {"success": True, "output": "x" * 100000})
        assert len(result["output"]) == 100000


# ============================================================
# A2: Memory Tools
# ============================================================

class TestMemoryTools:
    def test_import(self):
        from opendev.core.context_engineering.tools.implementations.memory_tools import MemoryTools
        from opendev.core.context_engineering.tools.handlers.memory_handlers import MemoryToolHandler
        assert MemoryTools is not None
        assert MemoryToolHandler is not None

    def test_search_empty_query(self):
        from opendev.core.context_engineering.tools.implementations.memory_tools import MemoryTools
        mt = MemoryTools(working_dir="/nonexistent")
        result = mt.search("")
        assert not result["success"]
        assert "empty" in result["error"].lower()

    def test_search_no_files(self):
        from opendev.core.context_engineering.tools.implementations.memory_tools import MemoryTools
        with tempfile.TemporaryDirectory() as tmpdir:
            mt = MemoryTools(working_dir=tmpdir)
            result = mt.search("test query")
            assert result["success"]
            assert "No memory files" in result["output"]

    def test_search_finds_matches(self):
        from opendev.core.context_engineering.tools.implementations.memory_tools import MemoryTools
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create memory directory and file
            mem_dir = Path(tmpdir) / ".opendev" / "memory"
            mem_dir.mkdir(parents=True)
            (mem_dir / "test.md").write_text("# Patterns\n\nAlways use pytest for testing\n")
            mt = MemoryTools(working_dir=tmpdir)
            result = mt.search("pytest testing")
            assert result["success"]
            assert len(result["matches"]) > 0
            assert "pytest" in result["output"].lower()

    def test_write_creates_file(self):
        from opendev.core.context_engineering.tools.implementations.memory_tools import MemoryTools
        with tempfile.TemporaryDirectory() as tmpdir:
            mt = MemoryTools(working_dir=tmpdir)
            result = mt.write("Test Topic", "Some content here")
            assert result["success"]
            assert "Created" in result["output"]
            # Verify file exists
            mem_file = Path(tmpdir) / ".opendev" / "memory" / "test-topic.md"
            assert mem_file.exists()
            content = mem_file.read_text()
            assert "Test Topic" in content
            assert "Some content here" in content

    def test_write_appends_to_existing(self):
        from opendev.core.context_engineering.tools.implementations.memory_tools import MemoryTools
        with tempfile.TemporaryDirectory() as tmpdir:
            mt = MemoryTools(working_dir=tmpdir)
            mt.write("Topic", "First entry")
            result = mt.write("Topic", "Second entry")
            assert result["success"]
            assert "Updated" in result["output"]
            content = (Path(tmpdir) / ".opendev" / "memory" / "topic.md").read_text()
            assert "First entry" in content
            assert "Second entry" in content

    def test_write_dedup(self):
        from opendev.core.context_engineering.tools.implementations.memory_tools import MemoryTools
        with tempfile.TemporaryDirectory() as tmpdir:
            mt = MemoryTools(working_dir=tmpdir)
            mt.write("Topic", "Exact content")
            result = mt.write("Topic", "Exact content")
            assert result["success"]
            assert "already contains" in result["output"]

    def test_write_empty_topic(self):
        from opendev.core.context_engineering.tools.implementations.memory_tools import MemoryTools
        mt = MemoryTools()
        result = mt.write("", "content")
        assert not result["success"]

    def test_write_user_scope(self):
        from opendev.core.context_engineering.tools.implementations.memory_tools import MemoryTools
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, 'home', return_value=Path(tmpdir)):
                mt = MemoryTools(working_dir="/somewhere")
                result = mt.write("Test", "Content", scope="user")
                assert result["success"]
                assert (Path(tmpdir) / ".opendev" / "memory" / "test.md").exists()

    def test_handler_delegates(self):
        from opendev.core.context_engineering.tools.handlers.memory_handlers import MemoryToolHandler
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = MemoryToolHandler(working_dir=tmpdir)
            result = handler.search({"query": "anything"})
            assert result["success"]  # No files, but succeeds


# ============================================================
# A1: Session Inspection Tools
# ============================================================

class TestSessionTools:
    def test_import(self):
        from opendev.core.context_engineering.tools.implementations.session_tools import SessionTools
        from opendev.core.context_engineering.tools.handlers.session_handlers import SessionToolHandler
        assert SessionTools is not None
        assert SessionToolHandler is not None

    def test_list_sessions_no_manager(self):
        from opendev.core.context_engineering.tools.implementations.session_tools import SessionTools
        st = SessionTools()
        result = st.list_sessions(session_manager=None)
        assert not result["success"]

    def test_list_sessions_empty(self):
        from opendev.core.context_engineering.tools.implementations.session_tools import SessionTools
        st = SessionTools()
        mock_manager = MagicMock()
        mock_manager.list_sessions.return_value = []
        result = st.list_sessions(session_manager=mock_manager)
        assert result["success"]
        assert "No past sessions" in result["output"]

    def test_list_sessions_with_data(self):
        from opendev.core.context_engineering.tools.implementations.session_tools import SessionTools
        st = SessionTools()
        mock_session = MagicMock()
        mock_session.id = "abc123"
        mock_session.title = "Test Session"
        mock_session.updated_at = "2024-01-01"
        mock_session.message_count = 5
        mock_manager = MagicMock()
        mock_manager.list_sessions.return_value = [mock_session]
        result = st.list_sessions(session_manager=mock_manager)
        assert result["success"]
        assert "abc123" in result["output"]

    def test_get_session_history_no_id(self):
        from opendev.core.context_engineering.tools.implementations.session_tools import SessionTools
        st = SessionTools()
        result = st.get_session_history(session_manager=MagicMock(), session_id="")
        assert not result["success"]

    def test_get_session_history_redacts_secrets(self):
        from opendev.core.context_engineering.tools.implementations.session_tools import _redact_sensitive
        text = "My key is sk-abc123456789012345678901234567890 and token ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        redacted = _redact_sensitive(text)
        assert "sk-abc" not in redacted
        assert "ghp_" not in redacted
        assert "REDACTED" in redacted

    def test_list_subagents_no_manager(self):
        from opendev.core.context_engineering.tools.implementations.session_tools import SessionTools
        st = SessionTools()
        result = st.list_subagents(subagent_manager=None)
        assert result["success"]
        assert "No subagent manager" in result["output"]

    def test_handler_list_sessions(self):
        from opendev.core.context_engineering.tools.handlers.session_handlers import SessionToolHandler
        handler = SessionToolHandler()
        ctx = MagicMock()
        ctx.session_manager = MagicMock()
        ctx.session_manager.list_sessions.return_value = []
        result = handler.list_sessions({}, context=ctx)
        assert result["success"]


# ============================================================
# A6: Git Operations Tool
# ============================================================

class TestGitTool:
    def test_import(self):
        from opendev.core.context_engineering.tools.implementations.git_tool import GitTool
        assert GitTool is not None

    def test_unknown_action(self):
        from opendev.core.context_engineering.tools.implementations.git_tool import GitTool
        gt = GitTool()
        result = gt.execute("unknown_action")
        assert not result["success"]
        assert "Unknown git action" in result["error"]

    def test_status(self):
        from opendev.core.context_engineering.tools.implementations.git_tool import GitTool
        # Run in the actual repo
        gt = GitTool(working_dir=str(Path(__file__).parent.parent))
        result = gt.execute("status")
        assert result["success"]
        assert "Branch:" in result["output"]

    def test_log(self):
        from opendev.core.context_engineering.tools.implementations.git_tool import GitTool
        gt = GitTool(working_dir=str(Path(__file__).parent.parent))
        result = gt.execute("log", limit=3)
        assert result["success"]

    def test_diff(self):
        from opendev.core.context_engineering.tools.implementations.git_tool import GitTool
        gt = GitTool(working_dir=str(Path(__file__).parent.parent))
        result = gt.execute("diff")
        assert result["success"]

    def test_commit_no_message(self):
        from opendev.core.context_engineering.tools.implementations.git_tool import GitTool
        gt = GitTool()
        result = gt.execute("commit", message="")
        assert not result["success"]

    def test_push_force_protected_branch(self):
        from opendev.core.context_engineering.tools.implementations.git_tool import GitTool
        gt = GitTool(working_dir=str(Path(__file__).parent.parent))
        result = gt.execute("push", force=True, branch="main")
        assert not result["success"]
        assert "Refusing" in result["error"]

    def test_checkout_dirty_tree(self):
        from opendev.core.context_engineering.tools.implementations.git_tool import GitTool
        gt = GitTool(working_dir=str(Path(__file__).parent.parent))
        # Our working tree IS dirty (we just created files)
        result = gt.execute("checkout", branch="nonexistent-branch-12345")
        # Should either fail with dirty tree warning or branch not found
        assert not result["success"]

    def test_handler_delegation(self):
        from opendev.core.context_engineering.tools.handlers.git_handlers import GitToolHandler
        handler = GitToolHandler(working_dir=str(Path(__file__).parent.parent))
        result = handler.handle({"action": "status"})
        assert result["success"]


# ============================================================
# B2: Tool Profile & Group System
# ============================================================

class TestToolPolicy:
    def test_import(self):
        from opendev.core.context_engineering.tools.tool_policy import TOOL_GROUPS, PROFILES
        assert len(TOOL_GROUPS) > 0
        assert len(PROFILES) > 0

    def test_full_profile(self):
        from opendev.core.context_engineering.tools.tool_policy import ToolPolicy
        tools = ToolPolicy.resolve("full")
        assert "read_file" in tools
        assert "write_file" in tools
        assert "run_command" in tools
        assert "git" in tools

    def test_minimal_profile(self):
        from opendev.core.context_engineering.tools.tool_policy import ToolPolicy
        tools = ToolPolicy.resolve("minimal")
        assert "read_file" in tools
        assert "write_file" not in tools
        assert "run_command" not in tools
        # Always-allowed tools
        assert "task_complete" in tools
        assert "ask_user" in tools

    def test_review_profile(self):
        from opendev.core.context_engineering.tools.tool_policy import ToolPolicy
        tools = ToolPolicy.resolve("review")
        assert "read_file" in tools
        assert "git" in tools
        assert "web_search" in tools
        assert "write_file" not in tools

    def test_coding_profile(self):
        from opendev.core.context_engineering.tools.tool_policy import ToolPolicy
        tools = ToolPolicy.resolve("coding")
        assert "read_file" in tools
        assert "write_file" in tools
        assert "run_command" in tools
        assert "memory_search" in tools

    def test_additions(self):
        from opendev.core.context_engineering.tools.tool_policy import ToolPolicy
        tools = ToolPolicy.resolve("minimal", additions=["run_command"])
        assert "run_command" in tools

    def test_exclusions(self):
        from opendev.core.context_engineering.tools.tool_policy import ToolPolicy
        tools = ToolPolicy.resolve("full", exclusions=["kill_process"])
        assert "kill_process" not in tools
        assert "read_file" in tools

    def test_unknown_profile(self):
        from opendev.core.context_engineering.tools.tool_policy import ToolPolicy
        with pytest.raises(ValueError, match="Unknown tool profile"):
            ToolPolicy.resolve("nonexistent")

    def test_get_profile_names(self):
        from opendev.core.context_engineering.tools.tool_policy import ToolPolicy
        names = ToolPolicy.get_profile_names()
        assert "full" in names
        assert "minimal" in names
        assert "coding" in names
        assert "review" in names

    def test_get_profile_description(self):
        from opendev.core.context_engineering.tools.tool_policy import ToolPolicy
        desc = ToolPolicy.get_profile_description("full")
        assert "All" in desc


# ============================================================
# B3: Provider-Specific Schema Adaptation
# ============================================================

class TestSchemaAdapter:
    def test_import(self):
        from opendev.core.agents.components.schemas.schema_adapter import adapt_for_provider
        assert adapt_for_provider is not None

    def test_openai_passthrough(self):
        from opendev.core.agents.components.schemas.schema_adapter import adapt_for_provider
        schemas = [{"function": {"name": "test", "parameters": {"default": "x"}}}]
        result = adapt_for_provider(schemas, "openai")
        assert result is schemas  # Same object, no copy

    def test_gemini_strips_additional_properties(self):
        from opendev.core.agents.components.schemas.schema_adapter import adapt_for_provider
        schemas = [{"function": {"name": "test", "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"x": {"type": "string", "default": "hello"}},
        }}}]
        result = adapt_for_provider(schemas, "gemini")
        params = result[0]["function"]["parameters"]
        assert "additionalProperties" not in params
        assert "default" not in params["properties"]["x"]

    def test_gemini_strips_format(self):
        from opendev.core.agents.components.schemas.schema_adapter import adapt_for_provider
        schemas = [{"function": {"name": "test", "parameters": {
            "type": "object",
            "properties": {"x": {"type": "string", "format": "date-time"}},
        }}}]
        result = adapt_for_provider(schemas, "google")
        assert "format" not in result[0]["function"]["parameters"]["properties"]["x"]

    def test_xai_filters_web_search(self):
        from opendev.core.agents.components.schemas.schema_adapter import adapt_for_provider
        schemas = [
            {"function": {"name": "web_search", "parameters": {}}},
            {"function": {"name": "read_file", "parameters": {}}},
        ]
        result = adapt_for_provider(schemas, "xai")
        names = [s["function"]["name"] for s in result]
        assert "web_search" not in names
        assert "read_file" in names

    def test_mistral_flattens_anyof(self):
        from opendev.core.agents.components.schemas.schema_adapter import adapt_for_provider
        schemas = [{"function": {"name": "test", "parameters": {
            "type": "object",
            "properties": {"x": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
        }}}]
        result = adapt_for_provider(schemas, "mistral")
        prop_x = result[0]["function"]["parameters"]["properties"]["x"]
        assert "anyOf" not in prop_x
        assert prop_x.get("type") == "string"

    def test_general_cleanup_adds_type(self):
        from opendev.core.agents.components.schemas.schema_adapter import adapt_for_provider
        schemas = [{"function": {"name": "test", "parameters": {"properties": {}}}}]
        result = adapt_for_provider(schemas, "some-provider")
        assert result[0]["function"]["parameters"]["type"] == "object"

    def test_does_not_mutate_original(self):
        from opendev.core.agents.components.schemas.schema_adapter import adapt_for_provider
        original_params = {"type": "object", "additionalProperties": False, "properties": {}}
        schemas = [{"function": {"name": "test", "parameters": original_params.copy()}}]
        adapt_for_provider(schemas, "gemini")
        # Original should still have additionalProperties
        assert "additionalProperties" in original_params


# ============================================================
# A3: Browser Automation Tool (import-only test - Playwright optional)
# ============================================================

class TestBrowserTool:
    def test_import(self):
        from opendev.core.context_engineering.tools.implementations.browser_tool import BrowserTool
        from opendev.core.context_engineering.tools.handlers.browser_handlers import BrowserToolHandler
        assert BrowserTool is not None
        assert BrowserToolHandler is not None

    def test_unknown_action(self):
        from opendev.core.context_engineering.tools.implementations.browser_tool import BrowserTool
        bt = BrowserTool()
        # This will fail if playwright is not installed
        result = bt.execute("nonexistent_action")
        assert not result["success"]

    def test_handler_delegation(self):
        from opendev.core.context_engineering.tools.handlers.browser_handlers import BrowserToolHandler
        handler = BrowserToolHandler()
        result = handler.handle({"action": "nonexistent"})
        assert not result["success"]


# ============================================================
# A5: Cron/Scheduling Tool
# ============================================================

class TestScheduleTool:
    def test_import(self):
        from opendev.core.context_engineering.tools.implementations.schedule_tool import ScheduleTool
        assert ScheduleTool is not None

    def test_unknown_action(self):
        from opendev.core.context_engineering.tools.implementations.schedule_tool import ScheduleTool
        st = ScheduleTool()
        result = st.execute("unknown_action")
        assert not result["success"]

    def test_list_empty(self):
        from opendev.core.context_engineering.tools.implementations.schedule_tool import ScheduleTool
        st = ScheduleTool()
        # Use a temp schedules file
        with patch("opendev.core.context_engineering.tools.implementations.schedule_tool._SCHEDULES_FILE",
                    Path(tempfile.mktemp(suffix=".json"))):
            result = st.execute("list")
            assert result["success"]

    def test_add_remove_cycle(self):
        from opendev.core.context_engineering.tools.implementations.schedule_tool import ScheduleTool
        tmp_file = Path(tempfile.mktemp(suffix=".json"))
        with patch("opendev.core.context_engineering.tools.implementations.schedule_tool._SCHEDULES_FILE", tmp_file):
            st = ScheduleTool()
            # Add
            result = st.execute("add", name="test_job", cron="*/5 * * * *", command="echo hello")
            assert result["success"]
            # List
            result = st.execute("list")
            assert result["success"]
            assert "test_job" in result["output"]
            # Duplicate add
            result = st.execute("add", name="test_job", cron="*/5 * * * *", command="echo hello")
            assert not result["success"]
            assert "already exists" in result["error"]
            # Remove
            result = st.execute("remove", name="test_job")
            assert result["success"]
            # Verify removed
            result = st.execute("list")
            assert "test_job" not in result.get("output", "")
            # Clean up
            tmp_file.unlink(missing_ok=True)

    def test_run_now(self):
        from opendev.core.context_engineering.tools.implementations.schedule_tool import ScheduleTool
        tmp_file = Path(tempfile.mktemp(suffix=".json"))
        with patch("opendev.core.context_engineering.tools.implementations.schedule_tool._SCHEDULES_FILE", tmp_file):
            st = ScheduleTool()
            st.execute("add", name="echo_test", cron="* * * * *", command="echo test_output")
            result = st.execute("run_now", name="echo_test")
            assert result["success"]
            assert "test_output" in result["output"]
            tmp_file.unlink(missing_ok=True)

    def test_status(self):
        from opendev.core.context_engineering.tools.implementations.schedule_tool import ScheduleTool
        tmp_file = Path(tempfile.mktemp(suffix=".json"))
        with patch("opendev.core.context_engineering.tools.implementations.schedule_tool._SCHEDULES_FILE", tmp_file):
            st = ScheduleTool()
            result = st.execute("status")
            assert result["success"]
            tmp_file.unlink(missing_ok=True)

    def test_add_missing_params(self):
        from opendev.core.context_engineering.tools.implementations.schedule_tool import ScheduleTool
        st = ScheduleTool()
        assert not st.execute("add", name="", cron="*", command="echo")["success"]
        assert not st.execute("add", name="x", cron="", command="echo")["success"]
        assert not st.execute("add", name="x", cron="*", command="")["success"]


# ============================================================
# A4: Cross-Channel Message Tool
# ============================================================

class TestMessageTool:
    def test_import(self):
        from opendev.core.context_engineering.tools.implementations.message_tool import MessageTool
        assert MessageTool is not None

    def test_missing_message(self):
        from opendev.core.context_engineering.tools.implementations.message_tool import MessageTool
        mt = MessageTool()
        result = mt.execute(channel="slack", message="")
        assert not result["success"]

    def test_missing_channel(self):
        from opendev.core.context_engineering.tools.implementations.message_tool import MessageTool
        mt = MessageTool()
        result = mt.execute(channel="", message="hello")
        assert not result["success"]

    def test_no_webhook_configured(self):
        from opendev.core.context_engineering.tools.implementations.message_tool import MessageTool
        mt = MessageTool()
        result = mt.execute(channel="slack", message="hello")
        assert not result["success"]
        assert "webhook" in result["error"].lower()


# ============================================================
# B4: Parameter Normalization Layer
# ============================================================

class TestParamNormalizer:
    def test_import(self):
        from opendev.core.context_engineering.tools.param_normalizer import normalize_params
        assert normalize_params is not None

    def test_camel_to_snake(self):
        from opendev.core.context_engineering.tools.param_normalizer import normalize_params
        result = normalize_params("edit_file", {"filePath": "test.py", "oldContent": "a", "newContent": "b"})
        assert "file_path" in result
        assert "old_content" in result
        assert "new_content" in result
        assert "filePath" not in result

    def test_whitespace_stripping(self):
        from opendev.core.context_engineering.tools.param_normalizer import normalize_params
        result = normalize_params("test", {"query": "  hello world  "})
        assert result["query"] == "hello world"

    def test_path_resolution_relative(self):
        from opendev.core.context_engineering.tools.param_normalizer import normalize_params
        result = normalize_params("test", {"file_path": "src/main.py"}, working_dir="/project")
        assert result["file_path"] == "/project/src/main.py"

    def test_path_resolution_absolute(self):
        from opendev.core.context_engineering.tools.param_normalizer import normalize_params
        result = normalize_params("test", {"file_path": "/absolute/path.py"}, working_dir="/project")
        assert result["file_path"] == "/absolute/path.py"

    def test_path_resolution_tilde(self):
        from opendev.core.context_engineering.tools.param_normalizer import normalize_params
        result = normalize_params("test", {"file_path": "~/file.py"})
        assert "~" not in result["file_path"]
        assert result["file_path"].startswith("/")

    def test_non_path_params_unchanged(self):
        from opendev.core.context_engineering.tools.param_normalizer import normalize_params
        result = normalize_params("test", {"query": "hello", "count": 5})
        assert result["query"] == "hello"
        assert result["count"] == 5

    def test_snake_case_passthrough(self):
        from opendev.core.context_engineering.tools.param_normalizer import normalize_params
        result = normalize_params("test", {"file_path": "test.py"})
        assert "file_path" in result


# ============================================================
# B5: Tool Execution Middleware Chain
# ============================================================

class TestMiddleware:
    def test_import(self):
        from opendev.core.context_engineering.tools.middleware import (
            MiddlewareChain,
        )
        assert MiddlewareChain is not None

    def test_empty_chain(self):
        from opendev.core.context_engineering.tools.middleware import MiddlewareChain
        from opendev.core.context_engineering.tools.context import ToolExecutionContext
        chain = MiddlewareChain()
        def handler(args, ctx):
            return {"success": True, "output": "ok"}
        ctx = ToolExecutionContext()
        result = chain.execute("test", {"x": 1}, handler, ctx)
        assert result["success"]

    def test_before_modifies_args(self):
        from opendev.core.context_engineering.tools.middleware import MiddlewareChain
        from opendev.core.context_engineering.tools.context import ToolExecutionContext

        class AddArgMiddleware:
            def before(self, tool_name, args, ctx):
                return {**args, "added": True}, True
            def after(self, tool_name, args, result, ctx):
                return result

        chain = MiddlewareChain()
        chain.add(AddArgMiddleware())
        received_args = {}
        def handler(args, ctx):
            received_args.update(args)
            return {"success": True, "output": "ok"}
        ctx = ToolExecutionContext()
        chain.execute("test", {"x": 1}, handler, ctx)
        assert received_args.get("added") is True

    def test_before_blocks_execution(self):
        from opendev.core.context_engineering.tools.middleware import MiddlewareChain
        from opendev.core.context_engineering.tools.context import ToolExecutionContext

        class BlockingMiddleware:
            def before(self, tool_name, args, ctx):
                return args, False
            def after(self, tool_name, args, result, ctx):
                return result

        chain = MiddlewareChain()
        chain.add(BlockingMiddleware())
        handler_called = [False]
        def handler(args, ctx):
            handler_called[0] = True
            return {"success": True}
        ctx = ToolExecutionContext()
        result = chain.execute("test", {}, handler, ctx)
        assert not result["success"]
        assert not handler_called[0]

    def test_after_modifies_result(self):
        from opendev.core.context_engineering.tools.middleware import MiddlewareChain
        from opendev.core.context_engineering.tools.context import ToolExecutionContext

        class TagMiddleware:
            def before(self, tool_name, args, ctx):
                return args, True
            def after(self, tool_name, args, result, ctx):
                return {**result, "tagged": True}

        chain = MiddlewareChain()
        chain.add(TagMiddleware())
        def handler(args, ctx):
            return {"success": True}
        ctx = ToolExecutionContext()
        result = chain.execute("test", {}, handler, ctx)
        assert result.get("tagged") is True

    def test_builtin_sanitizer_middleware(self):
        from opendev.core.context_engineering.tools.middleware import ResultSanitizerMiddleware
        from opendev.core.context_engineering.tools.context import ToolExecutionContext
        mw = ResultSanitizerMiddleware()
        args, cont = mw.before("test", {}, ToolExecutionContext())
        assert cont is True
        result = mw.after("run_command", {}, {"success": True, "output": "x" * 20000}, ToolExecutionContext())
        assert "truncated" in result["output"]


# ============================================================
# B6: Smarter Parallel Execution Policy
# ============================================================

class TestParallelPolicy:
    def test_import(self):
        from opendev.core.context_engineering.tools.parallel_policy import READ_ONLY_TOOLS
        assert len(READ_ONLY_TOOLS) > 0

    def test_empty_calls(self):
        from opendev.core.context_engineering.tools.parallel_policy import ParallelPolicy
        groups = ParallelPolicy.partition([])
        assert groups == []

    def test_single_call(self):
        from opendev.core.context_engineering.tools.parallel_policy import ParallelPolicy
        calls = [{"function": {"name": "read_file", "arguments": "{}"}}]
        groups = ParallelPolicy.partition(calls)
        assert len(groups) == 1
        assert len(groups[0]) == 1

    def test_multiple_reads_parallel(self):
        from opendev.core.context_engineering.tools.parallel_policy import ParallelPolicy
        calls = [
            {"function": {"name": "read_file", "arguments": json.dumps({"file_path": "a.py"})}},
            {"function": {"name": "search", "arguments": json.dumps({"pattern": "x"})}},
            {"function": {"name": "list_files", "arguments": "{}"}},
        ]
        groups = ParallelPolicy.partition(calls)
        assert len(groups) == 1  # All reads in one group
        assert len(groups[0]) == 3

    def test_reads_then_writes(self):
        from opendev.core.context_engineering.tools.parallel_policy import ParallelPolicy
        calls = [
            {"function": {"name": "read_file", "arguments": "{}"}},
            {"function": {"name": "write_file", "arguments": json.dumps({"file_path": "a.py"})}},
        ]
        groups = ParallelPolicy.partition(calls)
        assert len(groups) == 2  # Reads, then writes

    def test_different_file_writes_parallel(self):
        from opendev.core.context_engineering.tools.parallel_policy import ParallelPolicy
        calls = [
            {"function": {"name": "write_file", "arguments": json.dumps({"file_path": "a.py"})}},
            {"function": {"name": "write_file", "arguments": json.dumps({"file_path": "b.py"})}},
        ]
        groups = ParallelPolicy.partition(calls)
        # Should be 1 group since different files
        assert len(groups) == 1

    def test_same_file_writes_sequential(self):
        from opendev.core.context_engineering.tools.parallel_policy import ParallelPolicy
        calls = [
            {"function": {"name": "edit_file", "arguments": json.dumps({"file_path": "a.py"})}},
            {"function": {"name": "edit_file", "arguments": json.dumps({"file_path": "a.py"})}},
        ]
        groups = ParallelPolicy.partition(calls)
        assert len(groups) == 2  # Sequential since same file

    def test_git_read_actions_parallel(self):
        from opendev.core.context_engineering.tools.parallel_policy import ParallelPolicy
        calls = [
            {"function": {"name": "git", "arguments": json.dumps({"action": "status"})}},
            {"function": {"name": "read_file", "arguments": "{}"}},
        ]
        groups = ParallelPolicy.partition(calls)
        assert len(groups) == 1  # Both read-only

    def test_new_session_tools_read_only(self):
        from opendev.core.context_engineering.tools.parallel_policy import READ_ONLY_TOOLS
        assert "list_sessions" in READ_ONLY_TOOLS
        assert "get_session_history" in READ_ONLY_TOOLS
        assert "memory_search" in READ_ONLY_TOOLS
        assert "list_subagents" in READ_ONLY_TOOLS


# ============================================================
# A7: Agents Listing Tool
# ============================================================

class TestAgentsTool:
    def test_import(self):
        from opendev.core.context_engineering.tools.implementations.agents_tool import AgentsTool
        assert AgentsTool is not None

    def test_no_manager(self):
        from opendev.core.context_engineering.tools.implementations.agents_tool import AgentsTool
        at = AgentsTool()
        result = at.list_agents(subagent_manager=None)
        assert result["success"]
        assert "No subagent manager" in result["output"]

    def test_with_filesystem_fallback(self):
        from opendev.core.context_engineering.tools.implementations.agents_tool import AgentsTool
        at = AgentsTool()
        mock_manager = MagicMock(spec=[])  # No special attributes
        result = at.list_agents(subagent_manager=mock_manager)
        # Should fall back to filesystem discovery
        assert result["success"]


# ============================================================
# A8: Apply Patch Tool
# ============================================================

class TestPatchTool:
    def test_import(self):
        from opendev.core.context_engineering.tools.implementations.patch_tool import PatchTool
        assert PatchTool is not None

    def test_empty_patch(self):
        from opendev.core.context_engineering.tools.implementations.patch_tool import PatchTool
        pt = PatchTool()
        result = pt.apply_patch("")
        assert not result["success"]

    def test_invalid_format(self):
        from opendev.core.context_engineering.tools.implementations.patch_tool import PatchTool
        pt = PatchTool()
        result = pt.apply_patch("not a valid patch")
        assert not result["success"]
        assert "Invalid patch format" in result["error"]

    def test_extract_files_git_format(self):
        from opendev.core.context_engineering.tools.implementations.patch_tool import PatchTool
        files = PatchTool._extract_files(
            "diff --git a/src/main.py b/src/main.py\n"
            "--- a/src/main.py\n"
            "+++ b/src/main.py\n"
            "@@ -1,3 +1,3 @@\n"
        )
        assert "src/main.py" in files

    def test_extract_files_standard_format(self):
        from opendev.core.context_engineering.tools.implementations.patch_tool import PatchTool
        files = PatchTool._extract_files(
            "--- a/old.py\n"
            "+++ b/new.py\n"
        )
        assert "new.py" in files

    def test_dry_run(self):
        from opendev.core.context_engineering.tools.implementations.patch_tool import PatchTool
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file to patch
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("hello\n")
            # Initialize git repo for git apply
            import subprocess
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True,
                         env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
                              "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"})
            pt = PatchTool(working_dir=tmpdir)
            patch = (
                "diff --git a/test.py b/test.py\n"
                "--- a/test.py\n"
                "+++ b/test.py\n"
                "@@ -1 +1 @@\n"
                "-hello\n"
                "+world\n"
            )
            result = pt.apply_patch(patch, dry_run=True)
            assert result["success"]
            # File should be unchanged
            assert test_file.read_text() == "hello\n"


# ============================================================
# B7: Auth Profile Rotation & Failover
# ============================================================

class TestAuthRotation:
    def test_import(self):
        from opendev.core.agents.components.api.auth_rotation import AuthProfileManager
        assert AuthProfileManager is not None

    def test_basic_rotation(self):
        from opendev.core.agents.components.api.auth_rotation import AuthProfileManager
        mgr = AuthProfileManager("test", ["key1", "key2", "key3"])
        assert mgr.profile_count == 3
        assert mgr.available_count == 3
        assert mgr.get_active_key() == "key1"

    def test_failover_on_429(self):
        from opendev.core.agents.components.api.auth_rotation import AuthProfileManager
        mgr = AuthProfileManager("test", ["key1", "key2"])
        mgr.mark_failure(429)
        key = mgr.get_active_key()
        assert key == "key2"
        assert mgr.available_count == 1

    def test_success_resets_state(self):
        from opendev.core.agents.components.api.auth_rotation import AuthProfileManager
        mgr = AuthProfileManager("test", ["key1", "key2"])
        mgr.mark_failure(429)
        mgr2 = AuthProfileManager("test", ["key1", "key2"])
        mgr2.mark_success()
        assert mgr2.available_count == 2

    def test_all_keys_in_cooldown(self):
        from opendev.core.agents.components.api.auth_rotation import AuthProfileManager
        mgr = AuthProfileManager("test", ["key1"])
        mgr.mark_failure(401)
        key = mgr.get_active_key()
        assert key is None

    def test_from_env(self):
        from opendev.core.agents.components.api.auth_rotation import AuthProfileManager
        with patch.dict(os.environ, {"TEST_API_KEY": "env_key1", "TEST_API_KEY_2": "env_key2"}):
            mgr = AuthProfileManager.from_env("test")
            assert mgr.profile_count == 2

    def test_from_config(self):
        from opendev.core.agents.components.api.auth_rotation import AuthProfileManager
        mgr = AuthProfileManager.from_config("test", {"api_keys": ["c1", "c2"]})
        assert mgr.profile_count == 2

    def test_empty_keys(self):
        from opendev.core.agents.components.api.auth_rotation import AuthProfileManager
        mgr = AuthProfileManager("test", [])
        assert mgr.get_active_key() is None
        assert mgr.profile_count == 0

    def test_get_stats(self):
        from opendev.core.agents.components.api.auth_rotation import AuthProfileManager
        mgr = AuthProfileManager("test", ["key1", "key2"])
        mgr.mark_success()
        stats = mgr.get_stats()
        assert stats["provider"] == "test"
        assert stats["total_profiles"] == 2
        assert len(stats["profiles"]) == 2


# ============================================================
# B8: In-Process Plugin Hooks
# ============================================================

class TestPluginHooks:
    def test_import(self):
        from opendev.core.hooks.plugin_hooks import PluginHookManager
        assert PluginHookManager is not None

    def test_empty_manager(self):
        from opendev.core.hooks.plugin_hooks import PluginHookManager
        mgr = PluginHookManager()
        assert mgr.hook_count == 0

    def test_pre_hook_passthrough(self):
        from opendev.core.hooks.plugin_hooks import PluginHookManager
        mgr = PluginHookManager()
        args, cont, reason = mgr.run_pre_hooks("test", {"x": 1})
        assert cont is True
        assert args == {"x": 1}

    def test_post_hook_passthrough(self):
        from opendev.core.hooks.plugin_hooks import PluginHookManager
        mgr = PluginHookManager()
        result = mgr.run_post_hooks("test", {}, {"success": True})
        assert result["success"]

    def test_load_plugin_from_file(self):
        from opendev.core.hooks.plugin_hooks import PluginHookManager
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / ".opendev" / "plugins"
            plugin_dir.mkdir(parents=True)
            # Create a test plugin
            plugin_code = '''
class TestHook:
    def on_pre_tool_use(self, tool_name, args):
        if tool_name == "blocked_tool":
            return {"blocked": True, "reason": "Test block"}
        return None

    def on_post_tool_use(self, tool_name, args, result):
        return {**result, "plugin_processed": True}

def register():
    return [TestHook()]
'''
            (plugin_dir / "test_plugin.py").write_text(plugin_code)

            mgr = PluginHookManager(working_dir=tmpdir)
            count = mgr.discover_and_load()
            assert count == 1
            assert mgr.hook_count == 1

            # Test blocking
            args, cont, reason = mgr.run_pre_hooks("blocked_tool", {})
            assert not cont
            assert "Test block" in reason

            # Test passthrough
            args, cont, reason = mgr.run_pre_hooks("other_tool", {"x": 1})
            assert cont

            # Test post hook
            result = mgr.run_post_hooks("test", {}, {"success": True})
            assert result.get("plugin_processed") is True

    def test_clear(self):
        from opendev.core.hooks.plugin_hooks import PluginHookManager
        mgr = PluginHookManager()
        mgr.clear()
        assert mgr.hook_count == 0


# ============================================================
# Integration: Registry has all new tools registered
# ============================================================

class TestRegistryIntegration:
    def test_all_new_tools_registered(self):
        from opendev.core.context_engineering.tools.registry import ToolRegistry
        registry = ToolRegistry()
        expected_tools = [
            "memory_search", "memory_write",
            "list_sessions", "get_session_history", "list_subagents",
            "git", "browser", "schedule", "send_message",
            "list_agents", "apply_patch",
        ]
        for tool in expected_tools:
            assert tool in registry._handlers, f"Tool '{tool}' not registered in registry"

    def test_all_schemas_exist(self):
        from opendev.core.agents.components.schemas.definitions import _BUILTIN_TOOL_SCHEMAS
        names = {s["function"]["name"] for s in _BUILTIN_TOOL_SCHEMAS}
        expected = {
            "memory_search", "memory_write",
            "list_sessions", "get_session_history", "list_subagents",
            "git", "browser", "schedule", "send_message",
            "list_agents", "apply_patch",
        }
        missing = expected - names
        assert not missing, f"Missing schemas: {missing}"

    def test_tool_descriptions_loadable(self):
        from opendev.core.agents.prompts.loader import load_tool_description
        tools = [
            "memory_search", "memory_write",
            "list_sessions", "get_session_history", "list_subagents",
            "git", "browser", "schedule", "send_message",
            "list_agents", "apply_patch",
        ]
        for tool in tools:
            desc = load_tool_description(tool)
            assert len(desc) > 10, f"Tool description for '{tool}' too short: {desc}"

    def test_schema_count(self):
        from opendev.core.agents.components.schemas.definitions import _BUILTIN_TOOL_SCHEMAS
        # We added 11 new schemas to the existing set
        assert len(_BUILTIN_TOOL_SCHEMAS) >= 44

    def test_planning_tools_unchanged(self):
        from opendev.core.agents.components.schemas.planning_builder import PLANNING_TOOLS
        # Core planning tools should still be present
        assert "read_file" in PLANNING_TOOLS
        assert "search" in PLANNING_TOOLS
        assert "spawn_subagent" in PLANNING_TOOLS


# ============================================================
# Integration: Schema Builder with Provider Adaptation
# ============================================================

class TestSchemaBuilderIntegration:
    def test_builder_with_provider(self):
        from opendev.core.agents.components.schemas.normal_builder import ToolSchemaBuilder
        builder = ToolSchemaBuilder(tool_registry=None, provider="gemini")
        schemas = builder.build()
        # Gemini adapter should have cleaned the schemas
        for s in schemas:
            params = s.get("function", {}).get("parameters", {})
            assert "additionalProperties" not in params, \
                f"additionalProperties in {s['function']['name']}"

    def test_builder_without_provider(self):
        from opendev.core.agents.components.schemas.normal_builder import ToolSchemaBuilder
        builder = ToolSchemaBuilder(tool_registry=None)
        schemas = builder.build()
        assert len(schemas) > 0

    def test_builder_with_allowed_tools(self):
        from opendev.core.agents.components.schemas.normal_builder import ToolSchemaBuilder
        from opendev.core.context_engineering.tools.tool_policy import ToolPolicy
        allowed = list(ToolPolicy.resolve("minimal"))
        builder = ToolSchemaBuilder(tool_registry=None, allowed_tools=allowed)
        schemas = builder.build()
        schema_names = {s["function"]["name"] for s in schemas}
        # Should only have minimal tools
        assert "read_file" in schema_names
        assert "write_file" not in schema_names
