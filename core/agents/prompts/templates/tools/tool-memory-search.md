<!--
name: 'Tool Description: memory_search'
description: Search agent memory files
version: 1.0.0
-->

Search across all agent memory files for relevant past knowledge, patterns, and notes.

## Usage notes

- Searches OPENDEV.md, .opendev/memory/*.md (project), and ~/.opendev/memory/*.md (user)
- Uses keyword matching with relevance scoring
- Returns snippets with file paths and line ranges
- Use this to recall past decisions, patterns, debugging insights, or user preferences
- More efficient than manually reading memory files when you don't know which file contains what you need
