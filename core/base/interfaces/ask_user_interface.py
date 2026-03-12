"""Ask-user workflow interface shared across core components."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class AskUserInterface(Protocol):
    """Protocol for prompting the user with questions.

    Both ``WebAskUserManager.prompt_user`` and the TUI bridge callback
    conform to this protocol without any code changes.
    """

    def prompt_user(self, questions: List[Any]) -> Optional[Dict[str, Any]]:
        """Present questions to the user and collect answers.

        Args:
            questions: List of Question objects to present.

        Returns:
            Dictionary mapping question identifiers to selected answer(s),
            or ``None`` if the user cancelled or timed out.
        """
        ...
