"""Parallel execution policy for tool calls.

Determines which tool calls can be safely executed in parallel and partitions
them into ordered execution groups.
"""

from __future__ import annotations

from typing import Any

# Tools that are always safe to parallelize (read-only operations)
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        # File reading
        "read_file",
        "list_files",
        "search",
        "find_symbol",
        "find_referencing_symbols",
        "read_pdf",
        "analyze_image",
        # Process inspection
        "list_processes",
        "get_process_output",
        # Web (read-only)
        "fetch_url",
        "web_search",
        "capture_web_screenshot",
        "capture_screenshot",
        # Session/memory (read-only)
        "list_sessions",
        "get_session_history",
        "list_subagents",
        "memory_search",
        # Git (read-only actions)
        "git",  # Note: partitioner checks action param for git
        # Meta (read-only)
        "list_todos",
        "search_tools",
        "task_complete",
        # Agents listing
        "list_agents",
    }
)

# Git actions that are safe to parallelize
READ_ONLY_GIT_ACTIONS: frozenset[str] = frozenset(
    {
        "status",
        "diff",
        "log",
        "branch",
    }
)

# Tools that modify state and should generally run sequentially
WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "write_file",
        "edit_file",
        "run_command",
        "insert_before_symbol",
        "insert_after_symbol",
        "replace_symbol_body",
        "rename_symbol",
        "notebook_edit",
        "apply_patch",
        "memory_write",
        "kill_process",
        "write_todos",
        "update_todo",
        "complete_todo",
        "clear_todos",
        "send_message",
        "schedule",
    }
)


class ParallelPolicy:
    """Partitions tool calls into execution groups for optimal parallelism.

    Rules:
    1. All read-only tools can run in parallel
    2. Write tools that target different files can potentially run in parallel
    3. Everything else runs sequentially
    4. MCP tools with readOnly metadata can parallelize
    """

    @staticmethod
    def partition(tool_calls: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Partition tool calls into ordered execution groups.

        Each group can be executed in parallel. Groups must be executed
        in order (group 1 before group 2, etc.).

        Args:
            tool_calls: List of tool call dicts with 'function.name' and 'function.arguments'.

        Returns:
            List of groups, where each group is a list of tool calls
            that can be safely executed in parallel.
        """
        if len(tool_calls) <= 1:
            return [tool_calls] if tool_calls else []

        read_group: list[dict[str, Any]] = []
        write_group: list[dict[str, Any]] = []
        other_group: list[dict[str, Any]] = []

        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")

            if ParallelPolicy._is_read_only(tc):
                read_group.append(tc)
            elif name in WRITE_TOOLS:
                write_group.append(tc)
            else:
                other_group.append(tc)

        groups: list[list[dict[str, Any]]] = []

        # Group 1: All read-only tools (parallel)
        if read_group:
            groups.append(read_group)

        # Group 2: Write tools
        if write_group:
            # Check if writes target different files → can parallelize
            if ParallelPolicy._can_parallelize_writes(write_group):
                groups.append(write_group)
            else:
                # Sequential: each write is its own group
                for tc in write_group:
                    groups.append([tc])

        # Group 3: Everything else (sequential)
        for tc in other_group:
            groups.append([tc])

        return groups

    @staticmethod
    def _is_read_only(tool_call: dict[str, Any]) -> bool:
        """Check if a tool call is read-only."""
        name = tool_call.get("function", {}).get("name", "")

        # Standard read-only tools
        if name in READ_ONLY_TOOLS:
            # Special case: git tool depends on action
            if name == "git":
                import json

                try:
                    args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                    action = args.get("action", "")
                    return action in READ_ONLY_GIT_ACTIONS
                except (json.JSONDecodeError, TypeError):
                    return False
            return True

        # MCP tools: check readOnly metadata if available
        if name.startswith("mcp__"):
            # Conservative: treat as write unless we know otherwise
            return False

        return False

    @staticmethod
    def _can_parallelize_writes(writes: list[dict[str, Any]]) -> bool:
        """Check if write operations target different files (safe to parallelize)."""
        import json

        targets: set[str] = set()
        for tc in writes:
            name = tc.get("function", {}).get("name", "")
            try:
                args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                return False  # Can't determine target → sequential

            if name in ("write_file", "edit_file", "notebook_edit"):
                target = args.get("file_path") or args.get("notebook_path", "")
                if not target:
                    return False
                if target in targets:
                    return False  # Same file → must be sequential
                targets.add(target)
            else:
                # Non-file writes (run_command, etc.) → sequential
                return False

        return len(targets) > 1  # Only parallelize if multiple different files
