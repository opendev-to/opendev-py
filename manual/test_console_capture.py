#!/usr/bin/env python3
"""Test to see what console output is captured during query processing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from io import StringIO
from opendev.ui_textual.runner import TextualRunner
from opendev.models.message import Role


def test_console_capture():
    """Check what console output is being captured."""
    print("=" * 80)
    print("Testing Console Output Capture")
    print("=" * 80)

    # Create runner
    runner = TextualRunner(working_dir=Path.cwd())

    # Process a test query
    test_query = "hello"
    print(f"\n📝 Processing query: '{test_query}'")

    # Capture what _run_query captures
    session_before = runner.session_manager.get_current_session()
    messages_before = len(session_before.messages) if session_before else 0

    # Manually do what _run_query does
    print(f"\n🎯 Capturing console output...")

    with runner.repl.console.capture() as capture:
        runner.repl._process_query(test_query)

    console_output = capture.get()

    print(f"\n📄 Console output captured ({len(console_output)} chars):")
    print("─" * 80)
    print(console_output)
    print("─" * 80)

    # Check session
    session_after = runner.session_manager.get_current_session()
    new_messages = session_after.messages[messages_before:]

    assistant_messages = [msg for msg in new_messages if msg.role == Role.ASSISTANT]

    if assistant_messages:
        assistant_text = assistant_messages[0].content
        print(f"\n💬 Assistant message from session:")
        print("─" * 80)
        print(assistant_text)
        print("─" * 80)

        print(f"\n🔍 Comparison:")
        if assistant_text in console_output:
            print(f"   ❌ PROBLEM: Assistant message IS in console output!")
            print(f"   This will cause DUPLICATION when both are rendered!")
        else:
            print(f"   ✅ Good: Assistant message NOT in console output")

    return True


if __name__ == "__main__":
    test_console_capture()
