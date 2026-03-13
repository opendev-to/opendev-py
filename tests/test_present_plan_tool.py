"""Tests for PresentPlanTool validation."""

import tempfile
from pathlib import Path

from opendev.core.context_engineering.tools.implementations.present_plan_tool import PresentPlanTool


def test_rejects_trivially_short_plan():
    """Plan content under 100 chars should be rejected."""
    tool = PresentPlanTool()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("Plan placeholder")
        f.flush()
        result = tool.execute(plan_file_path=f.name)

    assert result["success"] is False
    assert "too short" in result["error"]
    assert "16 chars" in result["error"]


def test_rejects_empty_plan():
    """Empty plan file should be rejected."""
    tool = PresentPlanTool()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("")
        f.flush()
        result = tool.execute(plan_file_path=f.name)

    assert result["success"] is False
    assert "empty" in result["error"]


def test_rejects_missing_delimiters():
    """Plan without ---BEGIN PLAN--- delimiter should be rejected."""
    tool = PresentPlanTool()
    plan_no_delimiters = (
        "# Goal\n\n"
        "Refactor the authentication module to support OAuth2.\n\n"
        "## Implementation Steps\n\n"
        "1. Add OAuth2 provider configuration\n"
        "2. Implement token exchange flow\n"
        "3. Update session management to handle OAuth tokens\n"
        "4. Add unit tests for the new OAuth2 flow\n"
        "5. Update documentation\n"
    )
    assert len(plan_no_delimiters.strip()) >= 100

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(plan_no_delimiters)
        f.flush()
        result = tool.execute(plan_file_path=f.name)

    assert result["success"] is False
    assert "---BEGIN PLAN---" in result["error"]


def test_rejects_delimiters_but_no_steps():
    """Plan with delimiters but no Implementation Steps should be rejected."""
    tool = PresentPlanTool()
    plan_no_steps = (
        "---BEGIN PLAN---\n\n"
        "## Goal\n"
        "Refactor the authentication module to support OAuth2.\n\n"
        "## Context\n"
        "The current auth module uses session-based auth only.\n\n"
        "---END PLAN---\n"
    )
    assert len(plan_no_steps.strip()) >= 100

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(plan_no_steps)
        f.flush()
        result = tool.execute(plan_file_path=f.name)

    assert result["success"] is False
    assert "no parseable implementation steps" in result["error"].lower()


def test_accepts_well_structured_plan():
    """A plan with delimiters and numbered steps should pass validation."""
    tool = PresentPlanTool()
    real_plan = (
        "---BEGIN PLAN---\n\n"
        "## Goal\n"
        "Refactor the authentication module to support OAuth2.\n\n"
        "## Implementation Steps\n"
        "1. Add OAuth2 provider configuration\n"
        "2. Implement token exchange flow\n"
        "3. Update session management to handle OAuth tokens\n"
        "4. Add unit tests for the new OAuth2 flow\n"
        "5. Update documentation\n\n"
        "## Verification\n"
        "- `uv run pytest tests/test_oauth2.py` — unit tests pass\n"
        "- OAuth2 login works end-to-end in the CLI\n\n"
        "---END PLAN---\n"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(real_plan)
        f.flush()
        # No ui_callback => auto-approve fallback path
        result = tool.execute(plan_file_path=f.name)

    assert result["success"] is True
    assert result.get("plan_approved") is True


def test_rejects_plan_with_insufficient_verification():
    """Plan with fewer than 2 verification items should be rejected."""
    tool = PresentPlanTool()
    plan_weak_verification = (
        "---BEGIN PLAN---\n\n"
        "## Goal\n"
        "Refactor the authentication module to support OAuth2.\n\n"
        "## Implementation Steps\n"
        "1. Add OAuth2 provider configuration\n"
        "2. Implement token exchange flow\n"
        "3. Update session management to handle OAuth tokens\n\n"
        "## Verification\n"
        "- Run tests\n\n"
        "---END PLAN---\n"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(plan_weak_verification)
        f.flush()
        result = tool.execute(plan_file_path=f.name)

    assert result["success"] is False
    assert "verification" in result["error"].lower()


def test_rejects_missing_file():
    """Non-existent plan file should be rejected."""
    tool = PresentPlanTool()
    result = tool.execute(plan_file_path="/tmp/nonexistent_plan_12345.md")
    assert result["success"] is False
    assert "not found" in result["error"]
