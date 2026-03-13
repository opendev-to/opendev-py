"""Toast notification helpers for the TUI."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import App


class ToastVariant(str, Enum):
    INFO = "information"
    SUCCESS = "information"  # Textual uses "information" for positive
    WARNING = "warning"
    ERROR = "error"


def show_toast(
    app: App,
    message: str,
    variant: ToastVariant = ToastVariant.INFO,
    timeout: float = 4.0,
) -> None:
    """Show a toast notification in the TUI.

    Uses Textual's built-in notification system with standardized variants.
    """
    try:
        app.notify(message, severity=variant.value, timeout=timeout)
    except Exception:
        pass  # Gracefully handle if app isn't ready


def toast_info(app: App, message: str, timeout: float = 4.0) -> None:
    show_toast(app, message, ToastVariant.INFO, timeout)


def toast_success(app: App, message: str, timeout: float = 4.0) -> None:
    show_toast(app, message, ToastVariant.SUCCESS, timeout)


def toast_warning(app: App, message: str, timeout: float = 5.0) -> None:
    show_toast(app, message, ToastVariant.WARNING, timeout)


def toast_error(app: App, message: str, timeout: float = 6.0) -> None:
    show_toast(app, message, ToastVariant.ERROR, timeout)
