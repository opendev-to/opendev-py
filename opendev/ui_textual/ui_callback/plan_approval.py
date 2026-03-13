"""Mixin for plan mode approval in TextualUICallback."""

from __future__ import annotations

import logging
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CallbackPlanApprovalMixin:
    """Mixin handling plan mode approval, content display, and callback management."""

    def request_plan_mode_approval(self, message: str) -> bool:
        """Request user approval to enter plan mode.

        Args:
            message: Message explaining why entering plan mode

        Returns:
            True if user approved, False if denied

        Note:
            This is a placeholder implementation that auto-approves.
            Full UI dialog implementation should be added later.
        """
        # TODO: Implement full approval dialog with prompt_toolkit
        # For now, auto-approve to allow the feature to work
        logger.info(f"Plan mode approval requested: {message}")
        return True

    def display_plan_content(self, plan_content: str) -> None:
        """Display plan content in a bordered Markdown box in the conversation log."""
        if hasattr(self.conversation, "add_plan_content_box"):
            self._run_on_ui(self.conversation.add_plan_content_box, plan_content)

    def set_plan_approval_callback(self, callback) -> None:
        """Set the callback for plan approval UI interaction.

        Args:
            callback: Function that takes plan_content and returns dict with action/feedback
        """
        self._plan_approval_callback = callback

    def request_plan_approval(
        self,
        plan_content: str,
        allowed_prompts: Optional[list[Dict[str, str]]] = None,
    ) -> Dict[str, str]:
        """Request user approval of a completed plan.

        Args:
            plan_content: The full plan text
            allowed_prompts: Optional list of prompt-based permissions

        Returns:
            Dict with:
                - action: "approve_auto", "approve", or "modify"
                - feedback: Optional feedback for modification
        """
        callback = getattr(self, "_plan_approval_callback", None)
        if callback:
            return callback(plan_content)
        # Fallback: auto-approve (non-interactive contexts)
        return {"action": "approve", "feedback": ""}
