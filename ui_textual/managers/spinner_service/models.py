"""Spinner data models and configuration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional

from rich.text import Text

from opendev.ui_textual.style_tokens import (
    GREEN_BRIGHT,
    BLUE_BRIGHT,
    WARNING,
)


class SpinnerType(Enum):
    """Types of spinners with different rendering behaviors."""

    TOOL = auto()  # Main tool spinner - braille dots, 120ms
    THINKING = auto()  # Thinking spinner - braille dots, 120ms, 300ms min visibility
    TODO = auto()  # Todo panel - rotating arrows, 150ms
    NESTED = auto()  # Nested/subagent tool - flashing bullet, 300ms


@dataclass(frozen=True)
class SpinnerConfig:
    """Immutable configuration for a spinner animation type."""

    chars: tuple[str, ...]
    interval_ms: int
    style: str
    min_visible_ms: int = 0


SPINNER_CONFIGS: Dict[SpinnerType, SpinnerConfig] = {
    SpinnerType.TOOL: SpinnerConfig(
        chars=("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"),
        interval_ms=120,
        style=BLUE_BRIGHT,
    ),
    SpinnerType.THINKING: SpinnerConfig(
        chars=("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"),
        interval_ms=120,
        style=BLUE_BRIGHT,
        min_visible_ms=300,
    ),
    SpinnerType.NESTED: SpinnerConfig(
        chars=("⏺", "○"),
        interval_ms=300,
        style=GREEN_BRIGHT,  # Flashing animation uses green (not cyan like spinners)
    ),
    SpinnerType.TODO: SpinnerConfig(
        chars=("←", "↖", "↑", "↗", "→", "↘", "↓", "↙"),
        interval_ms=150,
        style=WARNING,
    ),
}


def get_spinner_config(spinner_type: SpinnerType) -> SpinnerConfig:
    """Get the configuration for a spinner type."""
    return SPINNER_CONFIGS.get(spinner_type, SPINNER_CONFIGS[SpinnerType.TOOL])


@dataclass
class SpinnerInstance:
    """State for a single active spinner."""

    spinner_id: str
    spinner_type: SpinnerType
    config: SpinnerConfig

    # Animation state
    frame_index: int = 0
    started_at: float = field(default_factory=time.monotonic)
    last_frame_at: float = field(default_factory=time.monotonic)

    # Content
    message: Text = field(default_factory=lambda: Text(""))
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Callback for rendering updates
    render_callback: Optional[Callable[["SpinnerFrame"], None]] = None

    # Stop handling
    stop_requested: bool = False
    stop_requested_at: float = 0.0


@dataclass
class SpinnerFrame:
    """Data passed to widget render callbacks each animation frame."""

    spinner_id: str
    spinner_type: SpinnerType
    char: str  # Current animation character
    frame_index: int  # Current frame number
    elapsed_seconds: int  # Seconds since spinner started
    message: Text  # Current message text
    style: str  # Style for the spinner character
    metadata: Dict[str, Any]  # Widget-specific data
