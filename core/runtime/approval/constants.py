"""Shared constants for the approval system.

Provides canonical definitions for safe commands, autonomy levels, and thinking
levels used by both TUI and Web UI approval managers.
"""

from __future__ import annotations

from enum import Enum


class AutonomyLevel(str, Enum):
    """Autonomy levels for command approval."""

    MANUAL = "Manual"
    SEMI_AUTO = "Semi-Auto"
    AUTO = "Auto"


class ThinkingLevel(str, Enum):
    """Thinking depth levels."""

    OFF = "Off"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


# Safe commands that can be auto-approved in Semi-Auto mode.
# Shared between TUI and Web approval managers.
SAFE_COMMANDS: list[str] = [
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "wc",
    "pwd",
    "echo",
    "which",
    "type",
    "file",
    "stat",
    "du",
    "df",
    "tree",
    "git status",
    "git log",
    "git diff",
    "git branch",
    "git show",
    "git remote",
    "git tag",
    "git stash list",
    "python --version",
    "python3 --version",
    "node --version",
    "npm --version",
    "cargo --version",
    "go version",
]


def is_safe_command(command: str) -> bool:
    """Check if a command is considered safe for auto-approval.

    Uses strict matching: the command must either equal a safe command exactly
    or start with it followed by a space (preventing e.g. ``cat`` from matching
    ``catastrophe``).

    Args:
        command: The command string to check.

    Returns:
        True if the command matches a known safe prefix.
    """
    if not command:
        return False
    cmd_lower = command.strip().lower()
    return any(
        cmd_lower == safe.lower() or cmd_lower.startswith(safe.lower() + " ")
        for safe in SAFE_COMMANDS
    )
