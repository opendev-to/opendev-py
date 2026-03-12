<!--
name: 'Tool Description: search'
description: Search for patterns in code using text or AST mode
version: 3.0.0
-->

Search for patterns in code. Supports 'text' mode (default, regex via ripgrep) and 'ast' mode (structural matching via ast-grep).

## Text mode

- Uses ripgrep under the hood — supports full regex syntax (e.g., "log.*Error", "function\\s+\\w+")
- Pattern syntax note: literal braces need escaping (use `interface\\{\\}` to find `interface{}` in Go)
- Filter files with `include_glob` (e.g., "*.js", "*.{ts,tsx}") or `file_type` (e.g., "py", "js", "rust") — file_type is more efficient
- Case insensitive search: set `case_insensitive=true`
- Context lines: set `context_lines` to include surrounding lines with each match
- Output modes via `output_mode`: "content" shows matching lines (default), "files_with_matches" shows only file paths, "count" shows match counts per file
- Multiline matching: by default patterns match within single lines. For cross-line patterns, set `multiline=true`
- Limit results with `max_results` (default 50)
- Be specific with the path to avoid slow searches across the entire codebase

## AST mode

- Use $VAR wildcards for structural patterns (e.g., "$A && $A()")
- Better for matching code structures regardless of whitespace or formatting

## Usage notes

- Results are capped at max_results matches and 30,000 chars total output
- ALWAYS use search for content searching. NEVER use run_command with grep or rg — the search tool has been optimized for correct permissions and access
- For simple, directed searches (specific class/function name), use search directly. For broader codebase exploration requiring multiple rounds, consider a subagent
- When to use search vs find_symbol: use search for text/regex matching across files; use find_symbol for structured code navigation via LSP (finds definitions, understands symbol hierarchy)
