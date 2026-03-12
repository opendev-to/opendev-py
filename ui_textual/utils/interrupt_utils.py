"""Utilities for handling interrupt messages across the UI."""

from rich.text import Text

from opendev.ui_textual.style_tokens import ERROR, GREY


def create_interrupt_message(message: str) -> str:
    """Create an interrupt message string with the special marker.

    This returns a string with the ::interrupted:: marker that will be
    processed by _write_generic_tool_result() in conversation_log.py to
    display with proper formatting (grey ⎿ prefix and red text).

    Args:
        message: The interrupt message content

    Returns:
        String with ::interrupted:: marker
    """
    return f"::interrupted:: {message.strip()}"


def create_interrupt_text(message: str) -> Text:
    """Create a Text object for interrupt messages with proper styling.

    This creates a Text object directly with the grey ⎿ prefix and
    bold red text formatting, bypassing the need for string markers.

    Args:
        message: The interrupt message content

    Returns:
        Text object with proper interrupt styling
    """
    line = Text("  ⎿  ", style=GREY)
    line.append(message.strip(), style=f"bold {ERROR}")
    return line


# Standard interrupt message constants
STANDARD_INTERRUPT_MESSAGE = "Interrupted · What should I do instead?"
THINKING_INTERRUPT_MESSAGE = STANDARD_INTERRUPT_MESSAGE
APPROVAL_INTERRUPT_MESSAGE = STANDARD_INTERRUPT_MESSAGE


def is_line_blank(line) -> bool:
    """Check if a conversation log line is visually blank.

    Handles Text objects (.plain), Strip objects (._segments), and string fallback.
    """
    try:
        if hasattr(line, "plain"):
            return not line.plain.strip()
        if hasattr(line, "_segments"):
            text = "".join(seg.text for seg in line._segments)
            return not text.strip()
        if hasattr(line, "text") and isinstance(line.text, str):
            return not line.text.strip()
        return not str(line).strip()
    except Exception:
        return False


def strip_trailing_blanks(conversation) -> None:
    """Remove ALL trailing blank lines from the conversation log.

    Loops until the last line has visible content, ensuring the interrupt
    message appears directly below the preceding content with no gap.
    """
    if not hasattr(conversation, "lines") or not hasattr(conversation, "_truncate_from"):
        return
    try:
        while len(conversation.lines) > 0:
            if is_line_blank(conversation.lines[-1]):
                conversation._truncate_from(len(conversation.lines) - 1)
            else:
                break
    except (TypeError, AttributeError):
        pass  # Graceful no-op if lines is a mock or unsupported type
