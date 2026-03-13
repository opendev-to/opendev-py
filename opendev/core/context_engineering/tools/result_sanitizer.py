"""Tool result sanitization — truncates large tool outputs before they enter LLM context."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class TruncationRule:
    """Per-tool truncation configuration."""
    max_chars: int
    strategy: str  # "head", "tail", "head_tail"
    head_ratio: float = 0.7  # For head_tail: proportion allocated to head


# Default rules by tool name (or prefix)
_DEFAULT_RULES: dict[str, TruncationRule] = {
    "run_command": TruncationRule(max_chars=8000, strategy="tail"),
    "read_file": TruncationRule(max_chars=15000, strategy="head"),
    "search": TruncationRule(max_chars=10000, strategy="head"),
    "list_files": TruncationRule(max_chars=10000, strategy="head"),
    "fetch_url": TruncationRule(max_chars=12000, strategy="head"),
    "web_search": TruncationRule(max_chars=10000, strategy="head"),
    "git": TruncationRule(max_chars=12000, strategy="head_tail"),
    "browser": TruncationRule(max_chars=5000, strategy="head"),
    "get_session_history": TruncationRule(max_chars=15000, strategy="tail"),
    "memory_search": TruncationRule(max_chars=10000, strategy="head"),
}

# MCP tools get a default rule
_MCP_DEFAULT_RULE = TruncationRule(max_chars=8000, strategy="head")

# Error results are always short
_ERROR_MAX_CHARS = 2000


class ToolResultSanitizer:
    """Sanitizes tool results by applying truncation and redaction rules.

    Integrates as a single pass in _format_tool_result() — the point where
    results enter the message history.
    """

    def __init__(self, custom_limits: Optional[dict[str, int]] = None) -> None:
        """Initialize with optional per-tool character limit overrides.

        Args:
            custom_limits: Dict mapping tool names to max character counts.
                          Overrides defaults from settings.json tool_result_limits.
        """
        self._rules = dict(_DEFAULT_RULES)
        if custom_limits:
            for tool_name, max_chars in custom_limits.items():
                if tool_name in self._rules:
                    self._rules[tool_name] = TruncationRule(
                        max_chars=max_chars,
                        strategy=self._rules[tool_name].strategy,
                        head_ratio=self._rules[tool_name].head_ratio,
                    )
                else:
                    self._rules[tool_name] = TruncationRule(
                        max_chars=max_chars, strategy="head"
                    )

    def sanitize(self, tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
        """Sanitize a tool result dict, truncating output if needed.

        Args:
            tool_name: Name of the tool that produced the result.
            result: The raw result dict (must have 'success', 'output'/'error' keys).

        Returns:
            The result dict with output potentially truncated. Original dict
            is NOT mutated — a shallow copy is returned when truncation occurs.
        """
        if not result.get("success", False):
            # Truncate error messages (they can be verbose too)
            error = result.get("error", "")
            if isinstance(error, str) and len(error) > _ERROR_MAX_CHARS:
                result = {**result, "error": self._truncate_head(error, _ERROR_MAX_CHARS)}
            return result

        output = result.get("output")
        if not output or not isinstance(output, str):
            return result

        rule = self._get_rule(tool_name)
        if rule is None or len(output) <= rule.max_chars:
            return result

        # Apply truncation
        original_len = len(output)
        truncated = self._apply_strategy(output, rule)

        marker = (
            f"\n\n[truncated: showing {len(truncated)} of {original_len} chars, "
            f"strategy={rule.strategy}]"
        )
        truncated += marker

        logger.debug(
            "Truncated %s result: %d -> %d chars (%s)",
            tool_name, original_len, len(truncated), rule.strategy,
        )

        return {**result, "output": truncated}

    def _get_rule(self, tool_name: str) -> Optional[TruncationRule]:
        """Look up the truncation rule for a tool."""
        # Exact match first
        if tool_name in self._rules:
            return self._rules[tool_name]
        # MCP tools
        if tool_name.startswith("mcp__"):
            return _MCP_DEFAULT_RULE
        # No rule → no truncation
        return None

    def _apply_strategy(self, text: str, rule: TruncationRule) -> str:
        """Apply a truncation strategy to text."""
        if rule.strategy == "tail":
            return self._truncate_tail(text, rule.max_chars)
        elif rule.strategy == "head_tail":
            return self._truncate_head_tail(text, rule.max_chars, rule.head_ratio)
        else:  # "head" (default)
            return self._truncate_head(text, rule.max_chars)

    @staticmethod
    def _truncate_head(text: str, max_chars: int) -> str:
        """Keep the beginning of the text."""
        return text[:max_chars]

    @staticmethod
    def _truncate_tail(text: str, max_chars: int) -> str:
        """Keep the end of the text (most recent output)."""
        return text[-max_chars:]

    @staticmethod
    def _truncate_head_tail(text: str, max_chars: int, head_ratio: float = 0.7) -> str:
        """Keep beginning and end, cut the middle."""
        head_size = int(max_chars * head_ratio)
        tail_size = max_chars - head_size
        head = text[:head_size]
        tail = text[-tail_size:]
        return head + "\n\n... [middle truncated] ...\n\n" + tail
