"""Trace viewer API routes — browse opendev JSONL session traces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/traces", tags=["traces"])

PROJECTS_DIR = Path.home() / ".opendev" / "projects"


@router.get("/projects")
async def list_projects() -> list[str]:
    """List project directories from ~/.opendev/projects/."""
    if not PROJECTS_DIR.exists():
        return []
    return sorted(
        d.name
        for d in PROJECTS_DIR.iterdir()
        if d.is_dir()
    )


@router.get("/projects/{project}/sessions")
async def list_sessions(project: str) -> list[dict[str, Any]]:
    """List sessions for a project.

    Uses sessions-index.json for speed; falls back to scanning .jsonl files.
    """
    project_dir = PROJECTS_DIR / project
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")

    sessions: list[dict[str, Any]] = []

    # Fast path: sessions-index.json
    index_file = project_dir / "sessions-index.json"
    if index_file.exists():
        try:
            index_data = json.loads(index_file.read_text())
            if isinstance(index_data, list):
                for entry in index_data:
                    sid = entry.get("session_id") or entry.get("id", "")
                    sessions.append({
                        "session_id": sid,
                        "title": entry.get("title", sid[:12]),
                        "message_count": entry.get("message_count", 0),
                        "timestamp": entry.get("updated_at") or entry.get("created_at", ""),
                        "working_dir": entry.get("working_dir", ""),
                    })
                return sorted(sessions, key=lambda s: s["timestamp"], reverse=True)
        except (json.JSONDecodeError, KeyError):
            pass  # fall through to scan

    # Slow path: scan .jsonl files
    for jsonl_file in sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        session_id = jsonl_file.stem
        msg_count = 0
        first_ts = ""
        title = session_id[:12]
        working_dir = ""

        try:
            with jsonl_file.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg_count += 1

                    if not first_ts:
                        first_ts = record.get("timestamp", "")

                    # Try to extract title from first user message
                    if (
                        title == session_id[:12]
                        and record.get("role") == "user"
                        and record.get("content")
                    ):
                        content = record["content"]
                        title = (content[:60] + "...") if len(content) > 60 else content

                    if not working_dir:
                        meta = record.get("metadata", {})
                        if isinstance(meta, dict):
                            working_dir = meta.get("working_dir", "")
        except OSError:
            continue

        sessions.append({
            "session_id": session_id,
            "title": title,
            "message_count": msg_count,
            "timestamp": first_ts,
            "working_dir": working_dir,
        })

    return sessions


@router.get("/projects/{project}/sessions/{session_id}")
async def get_session(project: str, session_id: str) -> list[dict[str, Any]]:
    """Load full JSONL transcript as array of ChatMessage records."""
    project_dir = PROJECTS_DIR / project
    jsonl_file = project_dir / f"{session_id}.jsonl"

    if not jsonl_file.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    messages: list[dict[str, Any]] = []
    with jsonl_file.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return messages
