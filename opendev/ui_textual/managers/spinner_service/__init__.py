"""Centralized spinner service for all UI animations."""

from opendev.ui_textual.managers.spinner_service.models import (
    SpinnerType,
    SpinnerConfig,
    SpinnerInstance,
    SpinnerFrame,
    SPINNER_CONFIGS,
    get_spinner_config,
)
from opendev.ui_textual.managers.spinner_service.service import SpinnerService

__all__ = [
    "SpinnerService",
    "SpinnerType",
    "SpinnerConfig",
    "SpinnerFrame",
    "SpinnerInstance",
    "SPINNER_CONFIGS",
    "get_spinner_config",
]
