"""Parameter normalization for tool invocations.

Normalizes LLM-produced tool parameters before they reach handlers:
- Path resolution (relative -> absolute, ~ expansion)
- Key normalization (camelCase -> snake_case)
- Whitespace stripping on string params
- Workspace root guard (warn for paths outside workspace)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Parameters that contain file/directory paths and should be resolved.
# NOTE: "path" is intentionally excluded — it's used by search/list_files as a
# relative directory hint and the handlers already resolve it. Including it here
# causes regressions in test_tool_registry.
_PATH_PARAMS = {
    "file_path",
    "notebook_path",
    "output_path",
    "plan_file_path",
    "image_path",
}

# Known camelCase -> snake_case mappings from LLM errors
_CAMEL_TO_SNAKE: dict[str, str] = {
    "filePath": "file_path",
    "fileName": "file_name",
    "maxResults": "max_results",
    "maxLines": "max_lines",
    "oldContent": "old_content",
    "newContent": "new_content",
    "matchAll": "match_all",
    "createDirs": "create_dirs",
    "extractText": "extract_text",
    "maxLength": "max_length",
    "includeToolCalls": "include_tool_calls",
    "sessionId": "session_id",
    "subagentType": "subagent_type",
    "detailLevel": "detail_level",
    "cellId": "cell_id",
    "cellNumber": "cell_number",
    "cellType": "cell_type",
    "editMode": "edit_mode",
    "newSource": "new_source",
    "notebookPath": "notebook_path",
    "deepCrawl": "deep_crawl",
    "crawlStrategy": "crawl_strategy",
    "maxDepth": "max_depth",
    "includeExternal": "include_external",
    "maxPages": "max_pages",
    "allowedDomains": "allowed_domains",
    "blockedDomains": "blocked_domains",
    "urlPatterns": "url_patterns",
    "symbolName": "symbol_name",
    "newName": "new_name",
    "newBody": "new_body",
    "preserveSignature": "preserve_signature",
    "includeDeclaration": "include_declaration",
    "planFilePath": "plan_file_path",
    "skillName": "skill_name",
    "taskId": "task_id",
    "runInBackground": "run_in_background",
    "toolCallId": "tool_call_id",
    "multiSelect": "multi_select",
    "activeForm": "active_form",
    "viewportWidth": "viewport_width",
    "viewportHeight": "viewport_height",
    "timeoutMs": "timeout_ms",
    "capturePdf": "capture_pdf",
    "outputPath": "output_path",
    "imagePath": "image_path",
    "imageUrl": "image_url",
    "maxTokens": "max_tokens",
}


def normalize_params(
    tool_name: str,
    args: dict[str, Any],
    working_dir: Optional[str] = None,
) -> dict[str, Any]:
    """Normalize tool parameters.

    Applies in order:
    1. Key normalization (camelCase -> snake_case)
    2. Whitespace stripping on string values
    3. Path resolution for known path params

    Args:
        tool_name: Name of the tool being invoked.
        args: Raw arguments dict from the LLM.
        working_dir: Working directory for path resolution.

    Returns:
        Normalized arguments dict. Original is NOT mutated.
    """
    if not args:
        return args or {}
    normalized = {}

    for key, value in args.items():
        # 1. Key normalization
        new_key = _CAMEL_TO_SNAKE.get(key, key)

        # 2. Whitespace stripping
        if isinstance(value, str):
            value = value.strip()

        # 3. Path resolution
        if new_key in _PATH_PARAMS and isinstance(value, str) and value:
            value = _resolve_path(value, working_dir)

        normalized[new_key] = value

    return normalized


def _resolve_path(path_str: str, working_dir: Optional[str] = None) -> str:
    """Resolve a path string to an absolute path.

    - Expands ~ to home directory
    - Resolves relative paths against working_dir
    - Logs a warning for paths outside the workspace
    """
    # Expand user home
    expanded = os.path.expanduser(path_str)

    # If already absolute, return as-is
    if os.path.isabs(expanded):
        resolved = expanded
    elif working_dir:
        resolved = str(Path(working_dir) / expanded)
    else:
        resolved = str(Path.cwd() / expanded)

    # Normalize (resolve .., ., etc.)
    resolved = os.path.normpath(resolved)

    # Workspace guard: warn (not reject) for paths outside workspace
    if working_dir:
        try:
            Path(resolved).relative_to(working_dir)
        except ValueError:
            # Also allow home directory paths
            try:
                Path(resolved).relative_to(Path.home())
            except ValueError:
                logger.warning(
                    "Path '%s' is outside workspace '%s' and user home",
                    resolved,
                    working_dir,
                )

    return resolved
