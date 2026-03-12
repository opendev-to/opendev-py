"""Typed event definitions for the OpenDev event bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from datetime import datetime


class EventType(str, Enum):
    """All event types in the system."""

    # Agent events
    AGENT_THINKING = "agent.thinking"
    AGENT_RESPONSE = "agent.response"
    AGENT_ERROR = "agent.error"

    # Tool events
    TOOL_START = "tool.start"
    TOOL_COMPLETE = "tool.complete"
    TOOL_ERROR = "tool.error"

    # File events
    FILE_CREATED = "file.created"
    FILE_MODIFIED = "file.modified"
    FILE_DELETED = "file.deleted"
    FILE_READ = "file.read"
    FILE_EXTERNAL_CHANGE = "file.external_change"

    # Session events
    SESSION_CREATED = "session.created"
    SESSION_RESUMED = "session.resumed"
    SESSION_SAVED = "session.saved"
    SESSION_ARCHIVED = "session.archived"
    SESSION_TITLE_SET = "session.title_set"

    # Context events
    CONTEXT_WARNING = "context.warning"
    CONTEXT_COMPACTION = "context.compaction"
    CONTEXT_OVERFLOW = "context.overflow"

    # MCP events
    MCP_CONNECTED = "mcp.connected"
    MCP_DISCONNECTED = "mcp.disconnected"
    MCP_ERROR = "mcp.error"

    # Permission events
    PERMISSION_REQUESTED = "permission.requested"
    PERMISSION_GRANTED = "permission.granted"
    PERMISSION_DENIED = "permission.denied"

    # UI events
    MODE_CHANGED = "ui.mode_changed"
    STATUS_UPDATE = "ui.status_update"


@dataclass
class Event:
    """Base event with type and payload."""

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""

    def __repr__(self) -> str:
        return f"Event({self.type.value}, source={self.source!r})"
