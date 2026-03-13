"""Shared dataclasses and constants for tool rendering."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import ClassVar, Dict, List


# Tree connector characters
TREE_BRANCH = "\u251c\u2500"
TREE_LAST = "\u2514\u2500"
TREE_VERTICAL = "\u2502"
TREE_CONTINUATION = "\u23bf"


@dataclass
class NestedToolState:
    """State tracking for a single nested tool call."""

    line_number: int
    tool_text: "Text"  # noqa: F821 – resolved at runtime via rich.text
    depth: int
    timer_start: float
    color_index: int = 0
    parent: str = ""
    tool_id: str = ""


@dataclass
class AgentInfo:
    """Info for a single parallel agent tracked by tool_call_id."""

    agent_type: str
    description: str
    tool_call_id: str
    line_number: int = 0  # Line for agent row
    status_line: int = 0  # Line for status/current tool
    tool_count: int = 0  # Total tool call count
    current_tool: str = "Initializing...."
    status: str = "running"  # running, completed, failed
    is_last: bool = False  # For tree connector rendering


@dataclass
class SingleAgentToolRecord:
    """Record of a single tool call within a subagent execution."""

    tool_name: str
    display_text: str
    success: bool = True
    elapsed_s: int = 0


@dataclass
class SingleAgentToolLine:
    """Tracks an active tool line within a single-agent display."""

    tool_id: str
    line_number: int
    display_text: str
    timer_start: float = field(default_factory=time.monotonic)
    color_index: int = 0
    completed: bool = False
    success: bool = True
    elapsed_s: int = 0  # Stored on completion for re-rendering during rotation


@dataclass
class SingleAgentInfo:
    """Info for a single (non-parallel) agent execution."""

    MAX_VISIBLE_TOOLS: ClassVar[int] = 3

    agent_type: str
    description: str
    tool_call_id: str
    header_line: int = 0  # Line for header
    tool_line: int = 0  # Line for current tool (first tool line)
    tool_count: int = 0
    current_tool: str = "Initializing..."
    status: str = "running"
    start_time: float = field(default_factory=time.monotonic)
    tool_records: List[SingleAgentToolRecord] = field(default_factory=list)
    failure_reason: str = ""  # Why the agent failed (API error, etc.)
    # Multi-tool tracking: tool_id -> SingleAgentToolLine
    active_tool_lines: Dict[str, "SingleAgentToolLine"] = field(default_factory=dict)
    overflow_line: int | None = None  # Line number for "+N more" text
    slot_lines: List[int] = field(default_factory=list)  # Fixed line numbers for visible slots
    hidden_count: int = 0  # Tools evicted from view (for overflow counter)


@dataclass
class ParallelAgentGroup:
    """Tracks a group of parallel agents for collapsed display."""

    agents: Dict[str, AgentInfo] = field(default_factory=dict)  # key = tool_call_id
    header_line: int = 0
    expanded: bool = False
    start_time: float = field(default_factory=time.monotonic)
    completed: bool = False


@dataclass
class AgentStats:
    """Stats tracking for a single agent type in a parallel group (legacy)."""

    tool_count: int = 0
    token_count: int = 0
    current_tool: str = ""
    status: str = "running"  # running, completed, failed
    agent_count: int = 1
    completed_count: int = 0
