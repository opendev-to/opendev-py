"""Shared API response models used by Web routes.

These models provide canonical serialization shapes for tool calls, messages,
and sessions, shared between ``routes/chat.py`` and ``routes/sessions.py``.
"""

from __future__ import annotations

import json
from typing import Dict, List

from pydantic import BaseModel


class ToolCallResponse(BaseModel):
    """Serialization view of a ToolCall for API responses."""

    id: str
    name: str
    parameters: Dict
    result: str | None = None
    error: str | None = None
    result_summary: str | None = None
    approved: bool | None = None
    nested_tool_calls: List["ToolCallResponse"] | None = None


# Required for self-referential Pydantic model
ToolCallResponse.model_rebuild()


class MessageResponse(BaseModel):
    """Response model for a chat message."""

    role: str
    content: str
    timestamp: str | None = None
    tool_calls: List[ToolCallResponse] | None = None
    thinking_trace: str | None = None
    reasoning_content: str | None = None


class SessionResponse(BaseModel):
    """Session information model."""

    id: str
    working_dir: str
    created_at: str
    updated_at: str
    message_count: int
    total_tokens: int
    title: str | None = None
    has_session_model: bool = False


def tool_call_to_response(tc: object) -> ToolCallResponse:
    """Recursively convert a ToolCall model to ToolCallResponse.

    Handles nested calls and coerces non-string results to JSON strings.

    Args:
        tc: A ``ToolCall`` instance (or any object with matching attributes).

    Returns:
        Serializable ``ToolCallResponse``.
    """
    nested = None
    if tc.nested_tool_calls:  # type: ignore[union-attr]
        nested = [tool_call_to_response(ntc) for ntc in tc.nested_tool_calls]  # type: ignore[union-attr]

    result = tc.result  # type: ignore[union-attr]
    if result is not None and not isinstance(result, str):
        try:
            result = json.dumps(result)
        except (TypeError, ValueError):
            result = str(result)

    return ToolCallResponse(
        id=tc.id,  # type: ignore[union-attr]
        name=tc.name,  # type: ignore[union-attr]
        parameters=tc.parameters,  # type: ignore[union-attr]
        result=result,
        error=tc.error,  # type: ignore[union-attr]
        result_summary=tc.result_summary,  # type: ignore[union-attr]
        approved=tc.approved,  # type: ignore[union-attr]
        nested_tool_calls=nested if nested else None,
    )
