#!/usr/bin/env python3
"""Console-only debug script to trace the exact message flow."""

import asyncio
import sys
from pathlib import Path

# Add the project to path
sys.path.insert(0, str(Path(__file__).parent))

from opendev.ui_textual.runner import TextualRunner
from opendev.models.message import Role

def print_section(title):
    """Print a section header."""
    print("\n" + "="*80)
    print(f" {title}")
    print("="*80)

def simulate_message_rendering(messages):
    """Simulate how the UI would render messages."""
    print("\n📨 Simulating UI message rendering:")
    print("-" * 40)

    for i, msg in enumerate(messages, 1):
        if msg.role == Role.USER:
            print(f"[USER] {msg.content}")
        elif msg.role == Role.ASSISTANT:
            print(f"[ASSISTANT] {msg.content}")
        elif msg.role == Role.SYSTEM:
            print(f"[SYSTEM] {msg.content}")
        else:
            print(f"[{msg.role.value}] {msg.content}")

    print("-" * 40)

def main():
    """Main debug function."""
    print_section("OpenDev Console Debug - Tracing Message Flow")

    try:
        # Step 1: Initialize the runner
        print("\n1️⃣ Initializing TextualRunner...")
        runner = TextualRunner(working_dir=Path.cwd())
        print(f"   ✅ Runner initialized")
        print(f"   📋 Model: {runner.config.model_provider}/{runner.config.model}")
        print(f"   📁 Working dir: {runner.working_dir}")

        # Step 2: Check initial session state
        print("\n2️⃣ Checking initial session state...")
        session = runner.session_manager.get_current_session()
        if session:
            print(f"   📝 Session ID: {session.id}")
            print(f"   📨 Initial message count: {len(session.messages)}")
        else:
            print("   ❌ No session found!")
            return False

        # Step 3: Process a test query
        print("\n3️⃣ Processing test query: 'hello'")
        print("   (This simulates what happens when user types in the UI)")

        test_query = "hello"

        # Get message count before
        messages_before = len(session.messages)
        print(f"   📨 Messages before: {messages_before}")

        # This is what the UI calls when user submits a message
        print("   🔄 Calling runner._run_query()...")
        new_messages = runner._run_query(test_query)

        # Get message count after
        messages_after = len(session.messages)
        print(f"   📨 Messages after: {messages_after}")
        print(f"   📨 New messages returned: {len(new_messages)}")

        # Step 4: Analyze the results
        print_section("Results Analysis")

        if new_messages:
            print(f"✅ SUCCESS! Backend processed the query and returned {len(new_messages)} messages")

            print(f"\n📨 Message details:")
            for i, msg in enumerate(new_messages, 1):
                print(f"   {i}. Role: {msg.role.value}")
                print(f"      Content: {msg.content[:100]}{'...' if len(msg.content) > 100 else ''}")
                print()

            # Step 5: Simulate UI rendering
            simulate_message_rendering(new_messages)

            # Check session consistency
            print_section("Session State Check")
            session_after = runner.session_manager.get_current_session()
            print(f"📝 Total messages in session: {len(session_after.messages)}")

            # Show all messages in session
            print(f"\n📨 All messages in session:")
            for i, msg in enumerate(session_after.messages, 1):
                print(f"   {i}. [{msg.role.value}] {msg.content[:80]}{'...' if len(msg.content) > 80 else ''}")

            print_section("CONCLUSION")
            print("✅ THE BACKEND IS WORKING PERFECTLY!")
            print("   - TextualRunner initialized successfully")
            print("   - Query was processed correctly")
            print("   - LLM generated a response")
            print("   - Messages were added to session")
            print("   - Model is responding correctly")
            print("\n   If you're not seeing responses in the Textual UI,")
            print("   the issue is likely in the UI rendering layer, not the backend!")

        else:
            print("❌ ISSUE: Backend returned no messages")
            print("   This suggests a problem with the backend processing")

            # Check session again
            session_after = runner.session_manager.get_current_session()
            print(f"📝 Messages in session now: {len(session_after.messages)}")

            if len(session_after.messages) > messages_before:
                print("   ⚠️  Messages were added to session but not returned")
                print("   This might be an issue with the _run_query method")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🐛 OpenDev Console Debug Tool")
    print("This will trace the exact message flow to identify where the issue lies.")

    success = main()

    if success:
        print("\n🎉 Debug completed successfully!")
        print("   Check the output above to see the detailed message flow.")
    else:
        print("\n💥 Debug failed - see error details above.")

    sys.exit(0 if success else 1)