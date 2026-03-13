"""Master list of built-in tool schemas used by OpenDev agents.

This module contains the complete schema definitions for all built-in tools.
These schemas are imported by ToolSchemaBuilder.

Tool descriptions are loaded from markdown templates in
``swecli/core/agents/prompts/templates/tools/``.
"""

from __future__ import annotations

from typing import Any

from opendev.core.agents.prompts.loader import load_tool_description

_BUILTIN_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": load_tool_description("write_file"),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path where the file should be created (e.g., 'app.py', 'src/main.js')",
                    },
                    "content": {
                        "type": "string",
                        "description": "The complete content to write to the file",
                    },
                    "create_dirs": {
                        "type": "boolean",
                        "description": "Whether to create parent directories if they don't exist",
                        "default": True,
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": load_tool_description("edit_file"),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path to the file to edit",
                    },
                    "old_content": {
                        "type": "string",
                        "description": "The exact text to find and replace in the file",
                    },
                    "new_content": {
                        "type": "string",
                        "description": "The new text to replace the old content with",
                    },
                    "match_all": {
                        "type": "boolean",
                        "description": "Whether to replace all occurrences (true) or just the first one (false)",
                        "default": False,
                    },
                },
                "required": ["file_path", "old_content", "new_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": load_tool_description("read_file"),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The path to the file to read",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "1-based line number to start reading from. Defaults to 1.",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Maximum number of lines to return. Defaults to 2000.",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": load_tool_description("list_files"),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The directory path to list",
                        "default": ".",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Optional glob pattern to filter files (e.g., '*.py', '**/*.js')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 100,
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum directory depth to traverse when listing without a glob pattern",
                        "default": 2,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": load_tool_description("search"),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern. For text mode: regex pattern. For AST mode: structural pattern with $VAR wildcards (e.g., '$A && $A()', 'console.log($MSG)')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search. Be specific to avoid timeouts.",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["text", "ast"],
                        "description": "Search type: 'text' for regex/string matching (default), 'ast' for structural code patterns",
                        "default": "text",
                    },
                    "lang": {
                        "type": "string",
                        "description": "Language hint for AST mode: python, typescript, javascript, go, rust, java, etc. Auto-detected if not specified.",
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "Case insensitive search (default false)",
                        "default": False,
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Number of context lines before and after each match",
                        "default": 0,
                    },
                    "include_glob": {
                        "type": "string",
                        "description": "Glob pattern to filter which files to search (e.g., '*.py', '*.{ts,tsx}')",
                    },
                    "file_type": {
                        "type": "string",
                        "description": "File type filter (e.g., 'py', 'js', 'rust', 'go', 'java'). More efficient than include_glob.",
                    },
                    "multiline": {
                        "type": "boolean",
                        "description": "Enable multiline matching where . matches newlines and patterns can span lines",
                        "default": False,
                    },
                    "output_mode": {
                        "type": "string",
                        "enum": ["content", "files_with_matches", "count"],
                        "description": "Output format: 'content' shows matching lines (default), 'files_with_matches' shows only file paths, 'count' shows match counts per file",
                        "default": "content",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matches to return",
                        "default": 50,
                    },
                },
                "required": ["pattern", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": load_tool_description("run_command"),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute",
                    },
                    "background": {
                        "type": "boolean",
                        "description": "Run command in background (returns immediately with PID). Use for long-running commands like servers.",
                        "default": False,
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_processes",
            "description": load_tool_description("list_processes"),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_process_output",
            "description": load_tool_description("get_process_output"),
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "integer",
                        "description": "Process ID returned by run_command with background=true",
                    },
                },
                "required": ["pid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": load_tool_description("kill_process"),
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "integer",
                        "description": "Process ID to kill",
                    },
                    "signal": {
                        "type": "integer",
                        "description": "Signal to send (15=SIGTERM, 9=SIGKILL)",
                        "default": 15,
                    },
                },
                "required": ["pid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": load_tool_description("fetch_url"),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch (must start with http:// or https://)",
                    },
                    "extract_text": {
                        "type": "boolean",
                        "description": "Whether to extract text from HTML (default: true)",
                        "default": True,
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum content length in characters (default: 50000)",
                        "default": 50000,
                    },
                    "deep_crawl": {
                        "type": "boolean",
                        "description": "Follow links and crawl multiple pages starting from the seed URL.",
                        "default": False,
                    },
                    "crawl_strategy": {
                        "type": "string",
                        "enum": ["bfs", "dfs", "best_first"],
                        "description": "Traversal strategy when deep_crawl is true. best_first (default) prioritizes relevance, bfs covers broadly, dfs follows a single branch.",
                        "default": "best_first",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth (beyond the seed page) to crawl when deep_crawl is enabled. Depth 0 is the starting page. Defaults to 1.",
                        "default": 1,
                    },
                    "include_external": {
                        "type": "boolean",
                        "description": "Allow crawling links that leave the starting domain when deep_crawl is enabled.",
                        "default": False,
                    },
                    "max_pages": {
                        "type": "integer",
                        "description": "Optional cap on the total number of pages to crawl when deep_crawl is enabled.",
                    },
                    "allowed_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional allow-list of domains to keep while deep crawling.",
                    },
                    "blocked_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional block-list of domains to skip while deep crawling.",
                    },
                    "url_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional glob-style URL patterns the crawler must match (e.g., '*docs*').",
                    },
                    "stream": {
                        "type": "boolean",
                        "description": "When true (and deep_crawl is enabled) stream pages as they are discovered before aggregation.",
                        "default": False,
                    },
                },
                "required": ["url"],
            },
        },
    },
    # ===== Web Search Tool =====
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": load_tool_description("web_search"),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to use. Be specific and include relevant keywords.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)",
                        "default": 10,
                    },
                    "allowed_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Only include search results from these domains (e.g., ['docs.python.org', 'stackoverflow.com'])",
                    },
                    "blocked_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Never include search results from these domains",
                    },
                },
                "required": ["query"],
            },
        },
    },
    # ===== Notebook Edit Tool =====
    {
        "type": "function",
        "function": {
            "name": "notebook_edit",
            "description": load_tool_description("notebook_edit"),
            "parameters": {
                "type": "object",
                "properties": {
                    "notebook_path": {
                        "type": "string",
                        "description": "Absolute path to the Jupyter notebook file (.ipynb)",
                    },
                    "new_source": {
                        "type": "string",
                        "description": "New source content for the cell. Required for replace and insert modes.",
                    },
                    "cell_id": {
                        "type": "string",
                        "description": "ID of the cell to edit. For insert mode, new cell is inserted after this cell.",
                    },
                    "cell_number": {
                        "type": "integer",
                        "description": "0-indexed cell position. Alternative to cell_id. For insert mode, new cell is inserted at this position.",
                    },
                    "cell_type": {
                        "type": "string",
                        "enum": ["code", "markdown"],
                        "description": "Cell type. Required for insert mode, optional for replace mode.",
                    },
                    "edit_mode": {
                        "type": "string",
                        "enum": ["replace", "insert", "delete"],
                        "default": "replace",
                        "description": "Operation type: replace (update existing cell), insert (add new cell), or delete (remove cell).",
                    },
                },
                "required": ["notebook_path", "new_source"],
            },
        },
    },
    # ===== Ask User Question Tool =====
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": load_tool_description("ask_user"),
            "parameters": {
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "description": "List of questions to ask (1-4 questions)",
                        "minItems": 1,
                        "maxItems": 4,
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {
                                    "type": "string",
                                    "description": "The complete question to ask. Should be clear and end with a question mark.",
                                },
                                "header": {
                                    "type": "string",
                                    "description": "Short label displayed as a chip/tag (max 12 chars). E.g., 'Auth method', 'Library'.",
                                    "maxLength": 12,
                                },
                                "options": {
                                    "type": "array",
                                    "description": "Available choices (2-4 options). An 'Other' option is added automatically.",
                                    "minItems": 2,
                                    "maxItems": 4,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "label": {
                                                "type": "string",
                                                "description": "Display text for the option (1-5 words).",
                                            },
                                            "description": {
                                                "type": "string",
                                                "description": "Explanation of what this option means or implies.",
                                            },
                                        },
                                        "required": ["label", "description"],
                                    },
                                },
                                "multiSelect": {
                                    "type": "boolean",
                                    "default": False,
                                    "description": "If true, allow selecting multiple options instead of just one.",
                                },
                            },
                            "required": ["question", "header", "options"],
                        },
                    },
                },
                "required": ["questions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_todos",
            "description": load_tool_description("write_todos"),
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": "List of todo items to create",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "Plain text task description. No markdown formatting.",
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                    "description": "Task status. Defaults to 'pending'.",
                                    "default": "pending",
                                },
                                "activeForm": {
                                    "type": "string",
                                    "description": "Present continuous form shown during execution (e.g., 'Running tests')",
                                },
                            },
                            "required": ["content"],
                        },
                    },
                },
                "required": ["todos"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": load_tool_description("update_todo"),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "ID of the to-do to update (shown in the panel).",
                    },
                    "title": {
                        "type": "string",
                        "description": "New title for this to-do item.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["todo", "doing", "done"],
                        "description": "Set to 'doing' when you start, 'done' when you finish.",
                    },
                    "log": {
                        "type": "string",
                        "description": "Append a log entry while working on this task.",
                    },
                    "expanded": {
                        "type": "boolean",
                        "description": "Show or hide logs beneath this to-do.",
                    },
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_todo",
            "description": load_tool_description("complete_todo"),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "ID of the to-do item to mark complete.",
                    },
                    "log": {
                        "type": "string",
                        "description": "Optional completion note.",
                    },
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": load_tool_description("list_todos"),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_todos",
            "description": load_tool_description("clear_todos"),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_browser",
            "description": load_tool_description("open_browser"),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL or file path to open in the browser. Supports: full URLs (http://example.com), localhost addresses (localhost:3000), and local file paths (index.html, ./app.html, /path/to/file.html). Local files are automatically converted to file:// URLs.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capture_screenshot",
            "description": load_tool_description("capture_screenshot"),
            "parameters": {
                "type": "object",
                "properties": {
                    "monitor": {
                        "type": "integer",
                        "description": "Monitor number to capture (default: 1 for primary monitor)",
                        "default": 1,
                    },
                    "region": {
                        "type": "object",
                        "description": "Optional region to capture (x, y, width, height). If not provided, captures full screen.",
                        "properties": {
                            "x": {"type": "integer", "description": "X coordinate"},
                            "y": {"type": "integer", "description": "Y coordinate"},
                            "width": {"type": "integer", "description": "Width in pixels"},
                            "height": {"type": "integer", "description": "Height in pixels"},
                        },
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": load_tool_description("analyze_image"),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Text prompt describing what to analyze in the image (e.g., 'Describe this image', 'What errors do you see?', 'Extract text from this image')",
                    },
                    "image_path": {
                        "type": "string",
                        "description": "Path to local image file (relative to working directory or absolute). Supports .jpg, .jpeg, .png, .gif, .webp. Takes precedence over image_url if both provided.",
                    },
                    "image_url": {
                        "type": "string",
                        "description": "URL of online image (must start with http:// or https://). Used only if image_path not provided.",
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "Maximum tokens in response (optional, defaults to config value)",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capture_web_screenshot",
            "description": load_tool_description("capture_web_screenshot"),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the web page to capture (must start with http:// or https://)",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Optional path to save screenshot (relative to working directory or absolute). If not provided, auto-generates filename in temp directory. For PDF, the .pdf extension will be automatically used.",
                    },
                    "capture_pdf": {
                        "type": "boolean",
                        "description": "If true, also capture a PDF version of the page. PDF is more reliable for very long pages. Both screenshot and PDF will be saved if enabled. Default: false",
                        "default": False,
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Maximum time to wait for page load in milliseconds. Default: 90000 (90 seconds). Complex sites with heavy JavaScript (like SaaS platforms, dashboards) may need 120000-180000ms.",
                        "default": 90000,
                    },
                    "viewport_width": {
                        "type": "integer",
                        "description": "Browser viewport width in pixels. Default: 1920",
                        "default": 1920,
                    },
                    "viewport_height": {
                        "type": "integer",
                        "description": "Browser viewport height in pixels. Default: 1080",
                        "default": 1080,
                    },
                },
                "required": ["url"],
            },
        },
    },
    # ===== Browser Automation Tool =====
    {
        "type": "function",
        "function": {
            "name": "browser",
            "description": load_tool_description("browser"),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "navigate",
                            "click",
                            "type",
                            "fill",
                            "screenshot",
                            "get_text",
                            "wait",
                            "evaluate",
                            "tabs_list",
                            "tab_close",
                            "back",
                            "forward",
                            "reload",
                        ],
                        "description": "Browser action to perform",
                    },
                    "target": {
                        "type": "string",
                        "description": "Target for the action: URL (navigate), CSS selector (click/type/fill/wait/get_text/screenshot), tab index (tab_close), or JS expression (evaluate)",
                    },
                    "value": {
                        "type": "string",
                        "description": "Value for the action: text (type/fill) or JavaScript code (evaluate)",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Action timeout in milliseconds (default: 10000)",
                        "default": 10000,
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ===== Schedule Tool =====
    {
        "type": "function",
        "function": {
            "name": "schedule",
            "description": load_tool_description("schedule"),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "add", "remove", "run_now", "status"],
                        "description": "Schedule action to perform",
                    },
                    "name": {
                        "type": "string",
                        "description": "Schedule name (for add/remove/run_now)",
                    },
                    "cron": {
                        "type": "string",
                        "description": "Cron expression (for add). Format: minute hour day-of-month month day-of-week",
                    },
                    "command": {
                        "type": "string",
                        "description": "Shell command to run (for add)",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ===== Message Tool =====
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": load_tool_description("send_message"),
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "enum": ["slack", "discord", "webhook"],
                        "description": "Channel to send to",
                    },
                    "message": {
                        "type": "string",
                        "description": "Message content",
                    },
                    "target": {
                        "type": "string",
                        "description": "Webhook URL (overrides configured default)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "markdown"],
                        "description": "Message format",
                        "default": "text",
                    },
                },
                "required": ["channel", "message"],
            },
        },
    },
    # ===== PDF Tool =====
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": load_tool_description("read_pdf"),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the PDF file (absolute or relative to working directory)",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    # ===== Symbol Tools (LSP-based) =====
    {
        "type": "function",
        "function": {
            "name": "find_symbol",
            "description": load_tool_description("find_symbol"),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "Name path pattern to search for. Examples: 'MyClass' (class), 'MyClass.method' (method in class), 'my_func' (function), 'My*' (wildcard)",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional file path to limit search scope. If not provided, searches the workspace.",
                    },
                },
                "required": ["symbol_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_referencing_symbols",
            "description": load_tool_description("find_referencing_symbols"),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "Name of the symbol to find references for",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to file where the symbol is defined (required to locate the symbol)",
                    },
                    "include_declaration": {
                        "type": "boolean",
                        "description": "Whether to include the declaration itself in results",
                        "default": True,
                    },
                },
                "required": ["symbol_name", "file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_before_symbol",
            "description": load_tool_description("insert_before_symbol"),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "Name of the symbol to insert before",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to file containing the symbol",
                    },
                    "content": {
                        "type": "string",
                        "description": "Code content to insert",
                    },
                },
                "required": ["symbol_name", "file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_after_symbol",
            "description": load_tool_description("insert_after_symbol"),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "Name of the symbol to insert after",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to file containing the symbol",
                    },
                    "content": {
                        "type": "string",
                        "description": "Code content to insert",
                    },
                },
                "required": ["symbol_name", "file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_symbol_body",
            "description": load_tool_description("replace_symbol_body"),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "Name of the symbol whose body to replace",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to file containing the symbol",
                    },
                    "new_body": {
                        "type": "string",
                        "description": "New body content for the symbol",
                    },
                    "preserve_signature": {
                        "type": "boolean",
                        "description": "Whether to keep the function/method signature (default: true)",
                        "default": True,
                    },
                },
                "required": ["symbol_name", "file_path", "new_body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_symbol",
            "description": load_tool_description("rename_symbol"),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "Current name of the symbol to rename",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to file where symbol is defined",
                    },
                    "new_name": {
                        "type": "string",
                        "description": "New name for the symbol",
                    },
                },
                "required": ["symbol_name", "file_path", "new_name"],
            },
        },
    },
    # ===== Git Tool =====
    {
        "type": "function",
        "function": {
            "name": "git",
            "description": load_tool_description("git"),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "status",
                            "diff",
                            "log",
                            "branch",
                            "checkout",
                            "commit",
                            "push",
                            "pull",
                            "stash",
                            "merge",
                            "create_pr",
                        ],
                        "description": "Git action to perform",
                    },
                    "branch": {
                        "type": "string",
                        "description": "Branch name (for checkout, merge, push, branch)",
                    },
                    "message": {
                        "type": "string",
                        "description": "Commit message (for commit) or stash message (for stash push)",
                    },
                    "file": {
                        "type": "string",
                        "description": "File path (for diff)",
                    },
                    "staged": {
                        "type": "boolean",
                        "description": "Show staged changes only (for diff)",
                        "default": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of entries to show (for log)",
                        "default": 10,
                    },
                    "remote": {
                        "type": "string",
                        "description": "Remote name (for push/pull)",
                        "default": "origin",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force push (uses --force-with-lease). Blocked for protected branches.",
                        "default": False,
                    },
                    "create": {
                        "type": "boolean",
                        "description": "Create new branch (for checkout -b)",
                        "default": False,
                    },
                    "title": {
                        "type": "string",
                        "description": "PR title (for create_pr)",
                    },
                    "body": {
                        "type": "string",
                        "description": "PR body/description (for create_pr)",
                    },
                    "base": {
                        "type": "string",
                        "description": "Base branch for PR (for create_pr)",
                    },
                    "name": {
                        "type": "string",
                        "description": "Branch name (for branch create/delete)",
                    },
                    "delete": {
                        "type": "boolean",
                        "description": "Delete the branch (for branch)",
                        "default": False,
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ===== Memory Tools =====
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": load_tool_description("memory_search"),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — matches against content in all memory files",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_write",
            "description": load_tool_description("memory_write"),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic name for the memory entry (used to generate filename)",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the memory file",
                    },
                    "file": {
                        "type": "string",
                        "description": "Optional specific filename (e.g., 'patterns.md'). Auto-generated from topic if not specified.",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["project", "user"],
                        "description": "Scope level: 'project' (.opendev/memory/) or 'user' (~/.opendev/memory/)",
                        "default": "project",
                    },
                },
                "required": ["topic", "content"],
            },
        },
    },
    # ===== Session Inspection Tools =====
    {
        "type": "function",
        "function": {
            "name": "list_sessions",
            "description": load_tool_description("list_sessions"),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of sessions to return (default: 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_session_history",
            "description": load_tool_description("get_session_history"),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "ID of the session to read (from list_sessions)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of messages to return (default: 50)",
                        "default": 50,
                    },
                    "include_tool_calls": {
                        "type": "boolean",
                        "description": "Include tool call details in output (default: false)",
                        "default": False,
                    },
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_subagents",
            "description": load_tool_description("list_subagents"),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    # ===== Agents Listing Tool =====
    {
        "type": "function",
        "function": {
            "name": "list_agents",
            "description": load_tool_description("list_agents"),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    # ===== Apply Patch Tool =====
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": load_tool_description("apply_patch"),
            "parameters": {
                "type": "object",
                "properties": {
                    "patch": {
                        "type": "string",
                        "description": "Unified diff patch content",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "Validate patch without applying (default: false)",
                        "default": False,
                    },
                },
                "required": ["patch"],
            },
        },
    },
    # ===== Task Completion Tool =====
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": load_tool_description("task_complete"),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": (
                            "Summary of what was accomplished. Include key details: "
                            "file paths created/modified, URLs, ports, commands to run, "
                            "or test results. "
                            "Be specific enough that the user can act on this summary alone."
                        ),
                    },
                    "status": {
                        "type": "string",
                        "enum": ["success", "partial", "failed"],
                        "description": "Completion status: 'success' if fully completed, 'partial' if some parts done, 'failed' if couldn't complete",
                        "default": "success",
                    },
                },
                "required": ["summary", "status"],
            },
        },
    },
    # MCP Tool Discovery (Token-Efficient)
    {
        "type": "function",
        "function": {
            "name": "search_tools",
            "description": load_tool_description("search_tools"),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query - matches tool names and descriptions. Use '*' or empty string to list all tools.",
                    },
                    "detail_level": {
                        "type": "string",
                        "enum": ["names", "brief", "full"],
                        "description": "Level of detail: 'names' (tool names only), 'brief' (names + one-line descriptions), 'full' (complete schemas including parameters)",
                        "default": "brief",
                    },
                    "server": {
                        "type": "string",
                        "description": "Optional: filter to specific MCP server name",
                    },
                },
                "required": ["query"],
            },
        },
    },
    # Skills System Tool
    {
        "type": "function",
        "function": {
            "name": "invoke_skill",
            "description": load_tool_description("invoke_skill"),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill to invoke. Can include namespace prefix (e.g., 'git:commit'). Leave empty to list available skills.",
                    },
                },
                "required": [],
            },
        },
    },
    # ===== Task Output Tool =====
    {
        "type": "function",
        "function": {
            "name": "get_subagent_output",
            "description": load_tool_description("get_subagent_output"),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task_id returned when a background subagent was spawned (NOT the tool_call_id). "
                        "Only subagents with run_in_background=true return a task_id.",
                    },
                    "block": {
                        "type": "boolean",
                        "description": "Whether to wait for completion. Set to false for non-blocking status check.",
                        "default": True,
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Maximum wait time in milliseconds (max 600000)",
                        "default": 30000,
                        "maximum": 600000,
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    # ===== Batch Tool =====
    {
        "type": "function",
        "function": {
            "name": "batch_tool",
            "description": load_tool_description("batch_tool"),
            "parameters": {
                "type": "object",
                "properties": {
                    "invocations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool": {
                                    "type": "string",
                                    "description": "Name of the tool to invoke",
                                },
                                "input": {
                                    "type": "object",
                                    "description": "Arguments to pass to the tool",
                                },
                            },
                            "required": ["tool", "input"],
                        },
                        "description": "List of tool invocations to execute",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["parallel", "serial"],
                        "description": "Execution mode: 'parallel' (concurrent) or 'serial' (sequential)",
                        "default": "parallel",
                    },
                },
                "required": ["invocations"],
            },
        },
    },
    # ===== Plan Presentation Tool =====
    {
        "type": "function",
        "function": {
            "name": "present_plan",
            "description": load_tool_description("present_plan"),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_file_path": {
                        "type": "string",
                        "description": "Absolute path to the plan file to present for approval.",
                    },
                },
                "required": ["plan_file_path"],
            },
        },
    },
]
