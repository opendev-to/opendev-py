<!--
name: 'Tool Description: memory_write'
description: Write or update agent memory
version: 1.0.0
-->

Write or update a memory entry to persist knowledge across sessions.

## Usage notes

- Saves to .opendev/memory/ (project-level) or ~/.opendev/memory/ (user-level, scope="user")
- Automatically generates filename from topic if not specified
- Appends to existing files to avoid duplicates
- Use for: stable patterns, architectural decisions, user preferences, recurring solutions
- Do NOT save: temporary state, in-progress work, speculative conclusions
