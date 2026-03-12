"""Tests for shared approval constants."""

from opendev.core.runtime.approval.constants import (
    SAFE_COMMANDS,
    AutonomyLevel,
    ThinkingLevel,
    is_safe_command,
)


class TestIsSafeCommand:
    """Tests for is_safe_command() strictness."""

    def test_exact_match(self):
        assert is_safe_command("ls") is True
        assert is_safe_command("cat") is True
        assert is_safe_command("pwd") is True

    def test_prefix_with_space(self):
        assert is_safe_command("ls -la") is True
        assert is_safe_command("cat /etc/hosts") is True
        assert is_safe_command("git status --short") is True

    def test_rejects_prefix_without_space(self):
        """Ensure 'cat' does not match 'catastrophe'."""
        assert is_safe_command("catastrophe") is False
        assert is_safe_command("categorical") is False
        assert is_safe_command("lsof") is False
        assert is_safe_command("finding") is False

    def test_case_insensitive(self):
        assert is_safe_command("LS") is True
        assert is_safe_command("Git Status") is True
        assert is_safe_command("CAT /etc/hosts") is True

    def test_empty_and_whitespace(self):
        assert is_safe_command("") is False
        assert is_safe_command("   ") is False

    def test_multi_word_safe_commands(self):
        assert is_safe_command("git status") is True
        assert is_safe_command("git log --oneline") is True
        assert is_safe_command("git stash list") is True
        assert is_safe_command("python --version") is True

    def test_unsafe_commands(self):
        assert is_safe_command("rm -rf /") is False
        assert is_safe_command("sudo apt install") is False
        assert is_safe_command("curl http://example.com") is False


class TestAutonomyLevel:
    def test_values(self):
        assert AutonomyLevel.MANUAL.value == "Manual"
        assert AutonomyLevel.SEMI_AUTO.value == "Semi-Auto"
        assert AutonomyLevel.AUTO.value == "Auto"

    def test_string_comparison(self):
        """AutonomyLevel(str, Enum) can be compared with plain strings."""
        assert AutonomyLevel.AUTO == "Auto"
        assert AutonomyLevel.SEMI_AUTO == "Semi-Auto"


class TestThinkingLevel:
    def test_values(self):
        assert ThinkingLevel.OFF.value == "Off"
        assert ThinkingLevel.LOW.value == "Low"
        assert ThinkingLevel.MEDIUM.value == "Medium"
        assert ThinkingLevel.HIGH.value == "High"

    def test_string_comparison(self):
        assert ThinkingLevel.MEDIUM == "Medium"


class TestWSMessageTypeIdentity:
    """Verify str enum identity for backward compatibility."""

    def test_tool_call_value(self):
        from opendev.web.protocol import WSMessageType

        assert WSMessageType.TOOL_CALL.value == "tool_call"
        assert WSMessageType.TOOL_CALL == "tool_call"

    def test_error_value(self):
        from opendev.web.protocol import WSMessageType

        assert WSMessageType.ERROR.value == "error"

    def test_mcp_namespaced(self):
        from opendev.web.protocol import WSMessageType

        assert WSMessageType.MCP_STATUS_CHANGED.value == "mcp:status_changed"


class TestSafeCommandsList:
    def test_not_empty(self):
        assert len(SAFE_COMMANDS) > 0

    def test_contains_basics(self):
        assert "ls" in SAFE_COMMANDS
        assert "git status" in SAFE_COMMANDS
        assert "go version" in SAFE_COMMANDS
