<!--
name: 'Tool Description: get_session_history'
description: Read conversation history from a past session
version: 1.0.0
-->

Read the conversation history from a past session by its ID.

## Usage notes

- Use list_sessions first to find session IDs
- Returns messages with role and content
- Sensitive data (API keys, tokens) is automatically redacted
- Set include_tool_calls=true to see tool invocation details
- Output is capped at 80KB to prevent context bloat
- Messages are returned newest-last (chronological order)
