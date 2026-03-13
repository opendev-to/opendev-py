"""Tool profile and group system for controlling tool access.

Defines tool groups (read, write, process, etc.) and profiles (minimal, review,
coding, full) that compose groups into permission sets. Profiles can be extended
with per-project additions/exclusions.
"""

from __future__ import annotations

from typing import Optional


# Tool groups — categorize tools by function
TOOL_GROUPS: dict[str, set[str]] = {
    "group:read": {
        "read_file", "list_files", "search", "find_symbol",
        "find_referencing_symbols", "read_pdf", "analyze_image",
    },
    "group:write": {
        "write_file", "edit_file", "insert_before_symbol",
        "insert_after_symbol", "replace_symbol_body", "rename_symbol",
        "notebook_edit", "apply_patch",
    },
    "group:process": {
        "run_command", "list_processes", "get_process_output", "kill_process",
    },
    "group:web": {
        "fetch_url", "web_search", "capture_web_screenshot",
        "capture_screenshot", "browser", "open_browser",
    },
    "group:git": {"git"},
    "group:session": {
        "list_sessions", "get_session_history", "spawn_subagent",
        "get_subagent_output", "list_subagents",
    },
    "group:memory": {"memory_search", "memory_write"},
    "group:meta": {
        "task_complete", "ask_user", "present_plan",
        "write_todos", "update_todo", "complete_todo", "list_todos", "clear_todos",
        "search_tools", "invoke_skill", "batch_tool",
    },
    "group:messaging": {"send_message"},
    "group:automation": {"schedule"},
    "group:thinking": set(),  # populated dynamically if thinking tools exist
    "group:mcp": set(),  # populated dynamically from discovered MCP tools
}


# Named profiles — compose groups into permission sets
PROFILES: dict[str, list[str]] = {
    "minimal": ["group:read", "group:meta"],
    "review": ["group:read", "group:meta", "group:web", "group:git", "group:session"],
    "coding": [
        "group:read", "group:write", "group:process", "group:web",
        "group:git", "group:meta", "group:session", "group:memory",
    ],
    "full": list(TOOL_GROUPS.keys()),
}

# Tools that are always allowed regardless of profile
ALWAYS_ALLOWED = {"task_complete", "ask_user"}


class ToolPolicy:
    """Resolves which tools are allowed based on profile, additions, and exclusions."""

    @staticmethod
    def resolve(
        profile: str = "full",
        additions: Optional[list[str]] = None,
        exclusions: Optional[list[str]] = None,
    ) -> set[str]:
        """Resolve the set of allowed tool names for a given profile.

        Args:
            profile: Named profile from PROFILES dict.
            additions: Individual tool names to add beyond the profile.
            exclusions: Individual tool names to remove from the profile.

        Returns:
            Set of allowed tool names.

        Raises:
            ValueError: If the profile name is unknown.
        """
        if profile not in PROFILES:
            raise ValueError(
                f"Unknown tool profile: '{profile}'. "
                f"Available: {', '.join(PROFILES.keys())}"
            )

        # Expand groups into tool names
        allowed: set[str] = set()
        for group_name in PROFILES[profile]:
            group_tools = TOOL_GROUPS.get(group_name, set())
            allowed.update(group_tools)

        # Always-allowed tools
        allowed.update(ALWAYS_ALLOWED)

        # Apply additions
        if additions:
            allowed.update(additions)

        # Apply exclusions
        if exclusions:
            for tool in exclusions:
                allowed.discard(tool)

        return allowed

    @staticmethod
    def get_profile_names() -> list[str]:
        """Return available profile names."""
        return list(PROFILES.keys())

    @staticmethod
    def get_group_names() -> list[str]:
        """Return available group names."""
        return list(TOOL_GROUPS.keys())

    @staticmethod
    def get_tools_in_group(group_name: str) -> set[str]:
        """Get tool names in a specific group."""
        return TOOL_GROUPS.get(group_name, set())

    @staticmethod
    def get_profile_description(profile: str) -> str:
        """Get a human-readable description of a profile."""
        descriptions = {
            "minimal": "Read-only tools + meta tools (for planning/exploration)",
            "review": "Read + web + git + session tools (for code review)",
            "coding": "Full development toolset without messaging/automation",
            "full": "All available tools (default)",
        }
        return descriptions.get(profile, f"Profile: {profile}")
