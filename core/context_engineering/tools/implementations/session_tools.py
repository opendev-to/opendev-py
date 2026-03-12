"""Session inspection tools — list sessions, read history, list subagents."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Max size for history output to prevent context bloat
_MAX_HISTORY_BYTES = 80_000

# Patterns for sensitive data redaction
_SENSITIVE_PATTERNS = [
    (re.compile(r"(sk-[a-zA-Z0-9]{20,})"), "[REDACTED_API_KEY]"),
    (re.compile(r"(ghp_[a-zA-Z0-9]{36,})"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"(xoxb-[a-zA-Z0-9-]+)"), "[REDACTED_SLACK_TOKEN]"),
    (
        re.compile(r"(eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,})"),
        "[REDACTED_JWT]",
    ),
    # Long base64 strings (likely secrets or binary data)
    (re.compile(r"[A-Za-z0-9+/]{100,}={0,2}"), "[REDACTED_BASE64]"),
]


def _redact_sensitive(text: str) -> str:
    """Redact API keys, tokens, and long base64 from text."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SessionTools:
    """Inspect past sessions and active subagents."""

    def list_sessions(
        self,
        session_manager: Any,
        limit: int = 20,
        project: Optional[str] = None,
    ) -> dict[str, Any]:
        """List past sessions with metadata.

        Args:
            session_manager: SessionManager instance
            limit: Max sessions to return
            project: Optional project filter (not used currently, returns current project)

        Returns:
            Result dict with session list
        """
        if not session_manager:
            return {"success": False, "error": "Session manager not available", "output": None}

        try:
            sessions = session_manager.list_sessions()
            sessions = sessions[:limit]

            if not sessions:
                return {
                    "success": True,
                    "output": "No past sessions found.",
                    "sessions": [],
                }

            output_parts = [f"Found {len(sessions)} sessions:\n"]
            session_list = []

            for s in sessions:
                title = getattr(s, "title", "") or "Untitled"
                session_id = getattr(s, "id", "unknown")
                updated = str(getattr(s, "updated_at", ""))
                msg_count = getattr(s, "message_count", 0)

                output_parts.append(
                    f"  [{session_id[:8]}] {title} " f"({msg_count} msgs, updated {updated})"
                )
                session_list.append(
                    {
                        "id": session_id,
                        "title": title,
                        "updated_at": updated,
                        "message_count": msg_count,
                    }
                )

            return {
                "success": True,
                "output": "\n".join(output_parts),
                "sessions": session_list,
            }
        except Exception as e:
            logger.error("Failed to list sessions: %s", e, exc_info=True)
            return {"success": False, "error": f"Failed to list sessions: {e}", "output": None}

    def get_session_history(
        self,
        session_manager: Any,
        session_id: str,
        limit: int = 50,
        include_tool_calls: bool = False,
    ) -> dict[str, Any]:
        """Read conversation history from a past session.

        Args:
            session_manager: SessionManager instance
            session_id: Session ID to load
            limit: Max messages to return
            include_tool_calls: Whether to include tool call details

        Returns:
            Result dict with message history
        """
        if not session_manager:
            return {"success": False, "error": "Session manager not available", "output": None}
        if not session_id:
            return {"success": False, "error": "session_id is required", "output": None}

        try:
            # Try loading transcript (JSONL format)
            try:
                messages = session_manager.load_transcript(session_id)
            except FileNotFoundError:
                # Try loading full session
                session = session_manager.get_session_by_id(session_id)
                messages = session.messages

            if not messages:
                return {
                    "success": True,
                    "output": f"Session {session_id} has no messages.",
                    "messages": [],
                }

            # Limit messages
            messages = messages[-limit:] if len(messages) > limit else messages

            output_parts = [f"Session {session_id} — {len(messages)} messages:\n"]
            msg_list = []
            total_size = 0

            for msg in messages:
                role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                content = str(msg.content) if msg.content else ""

                # Skip tool role messages unless requested
                if role == "tool" and not include_tool_calls:
                    continue

                # Redact sensitive data
                content = _redact_sensitive(content)

                # Truncate individual messages
                if len(content) > 2000:
                    content = content[:2000] + "... [truncated]"

                total_size += len(content)
                if total_size > _MAX_HISTORY_BYTES:
                    output_parts.append(f"\n[truncated: reached {_MAX_HISTORY_BYTES} byte limit]")
                    break

                output_parts.append(f"[{role}]: {content}")
                msg_list.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )

            return {
                "success": True,
                "output": "\n\n".join(output_parts),
                "messages": msg_list,
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": f"Session {session_id} not found",
                "output": None,
            }
        except Exception as e:
            logger.error("Failed to get session history: %s", e, exc_info=True)
            return {"success": False, "error": f"Failed to load session: {e}", "output": None}

    def list_subagents(
        self,
        subagent_manager: Any,
    ) -> dict[str, Any]:
        """List active and recent subagents with status.

        Args:
            subagent_manager: SubAgentManager instance

        Returns:
            Result dict with subagent list
        """
        if not subagent_manager:
            return {
                "success": True,
                "output": "No subagent manager configured. No subagents are running.",
                "subagents": [],
            }

        try:
            # Check if manager tracks background tasks
            subagents = []
            if hasattr(subagent_manager, "get_active_tasks"):
                tasks = subagent_manager.get_active_tasks()
                for task in tasks:
                    subagents.append(
                        {
                            "id": task.get("id", "unknown"),
                            "status": task.get("status", "unknown"),
                            "description": task.get("description", ""),
                            "type": task.get("type", "general-purpose"),
                        }
                    )

            if not subagents:
                return {
                    "success": True,
                    "output": "No active subagents.",
                    "subagents": [],
                }

            output_parts = [f"Active subagents ({len(subagents)}):\n"]
            for sa in subagents:
                output_parts.append(
                    f"  [{sa['id'][:8]}] {sa['type']} — {sa['status']}: {sa['description']}"
                )

            return {
                "success": True,
                "output": "\n".join(output_parts),
                "subagents": subagents,
            }
        except Exception as e:
            logger.error("Failed to list subagents: %s", e, exc_info=True)
            return {"success": False, "error": f"Failed to list subagents: {e}", "output": None}
