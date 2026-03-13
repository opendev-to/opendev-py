"""EditTool class - file editing with diff preview and 9-pass fuzzy matching."""

import logging
import shutil
import threading
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from opendev.models.config import AppConfig
from opendev.models.operation import EditResult, Operation
from opendev.core.context_engineering.tools.implementations.base import BaseTool
from opendev.core.context_engineering.tools.implementations.diff_preview import DiffPreview, Diff
from opendev.core.context_engineering.tools.implementations.edit_tool.replacers import (
    _REPLACER_CHAIN,
    _normalize_line_endings,
)

if TYPE_CHECKING:
    from opendev.core.runtime.task_monitor import TaskMonitor

_LOG = logging.getLogger(__name__)


class EditTool(BaseTool):
    """Tool for editing existing files with diff preview."""

    _file_locks: dict[str, threading.Lock] = {}
    _lock_registry_lock = threading.Lock()

    @classmethod
    def _get_file_lock(cls, file_path: str) -> threading.Lock:
        """Get or create a lock for the given file path.

        Args:
            file_path: Absolute path to the file.

        Returns:
            A threading.Lock dedicated to that file path.
        """
        with cls._lock_registry_lock:
            if file_path not in cls._file_locks:
                cls._file_locks[file_path] = threading.Lock()
            return cls._file_locks[file_path]

    @property
    def name(self) -> str:
        """Tool name."""
        return "edit_file"

    @property
    def description(self) -> str:
        """Tool description."""
        return "Edit an existing file with search and replace"

    def _find_content(self, original: str, old_content: str) -> tuple[bool, str]:
        """Find content in file using 9-pass fuzzy matching chain.

        Tries 9 different matching strategies in order of strictness:
        1. SimpleReplacer - exact string match
        2. LineTrimmedReplacer - match trimmed lines
        3. BlockAnchorReplacer - anchor first/last lines, similarity for middle
        4. WhitespaceNormalizedReplacer - normalize all whitespace
        5. IndentationFlexibleReplacer - ignore indentation differences
        6. EscapeNormalizedReplacer - unescape common escape sequences
        7. TrimmedBoundaryReplacer - find trimmed boundaries
        8. ContextAwareReplacer - use surrounding context for matching
        9. MultiOccurrenceReplacer - trimmed exact match as last resort

        Args:
            original: The original file content
            old_content: The content to find

        Returns:
            (found, actual_content) - actual_content is what should be replaced
        """
        original = _normalize_line_endings(original)
        old_content = _normalize_line_endings(old_content)

        for replacer in _REPLACER_CHAIN:
            result = replacer.find(original, old_content)
            if result is not None:
                if replacer.name != "simple":
                    _LOG.debug("Edit matched via %s replacer", replacer.name)
                return (True, result)

        return (False, old_content)

    def __init__(self, config: AppConfig, working_dir: Path):
        """Initialize edit tool.

        Args:
            config: Application configuration
            working_dir: Working directory for operations
        """
        self.config = config
        self.working_dir = working_dir
        self.diff_preview = DiffPreview()

    def edit_file(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        match_all: bool = False,
        dry_run: bool = False,
        backup: bool = True,
        operation: Optional[Operation] = None,
        task_monitor: Optional["TaskMonitor"] = None,
    ) -> EditResult:
        """Edit file by replacing old_content with new_content.

        Args:
            file_path: Path to file to edit
            old_content: Content to find and replace
            new_content: New content to insert
            match_all: Replace all occurrences (default: first only)
            dry_run: If True, don't actually modify file
            backup: Create backup before editing
            operation: Operation object for tracking
            task_monitor: Optional task monitor for interrupt checking

        Returns:
            EditResult with operation details

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If edit is not permitted
            ValueError: If old_content not found or not unique
        """
        # Check for interrupt before starting
        if task_monitor and task_monitor.should_interrupt():
            error = "Interrupted before edit"
            if operation:
                operation.mark_failed(error)
            return EditResult(
                success=False,
                file_path=file_path,
                lines_added=0,
                lines_removed=0,
                error=error,
                operation_id=operation.id if operation else None,
                interrupted=True,
            )

        # Resolve path
        path = self._resolve_path(file_path)

        # Check if file exists
        if not path.exists():
            error = f"File not found: {path}"
            if operation:
                operation.mark_failed(error)
            return EditResult(
                success=False,
                file_path=str(path),
                lines_added=0,
                lines_removed=0,
                error=error,
                operation_id=operation.id if operation else None,
            )

        # Check write permissions
        if not self.config.permissions.file_write.is_allowed(str(path)):
            error = f"Editing {path} is not permitted by configuration"
            if operation:
                operation.mark_failed(error)
            return EditResult(
                success=False,
                file_path=str(path),
                lines_added=0,
                lines_removed=0,
                error=error,
                operation_id=operation.id if operation else None,
            )

        try:
            # Serialize concurrent edits to the same file
            with self._get_file_lock(str(path)):
                # Read original content
                with open(path, "r", encoding="utf-8") as f:
                    original = f.read()

                # Find old_content with fuzzy matching fallback
                found, actual_old_content = self._find_content(original, old_content)
                if not found:
                    error = f"Content not found in file: {old_content[:50]}..."
                    if operation:
                        operation.mark_failed(error)
                    return EditResult(
                        success=False,
                        file_path=str(path),
                        lines_added=0,
                        lines_removed=0,
                        error=error,
                        operation_id=operation.id if operation else None,
                    )

                # Use the actual content found in file for subsequent operations
                old_content = actual_old_content

                # Check if old_content is unique (if not match_all)
                count = original.count(old_content)
                if not match_all and count > 1:
                    # Find line numbers of each occurrence to help LLM provide more context
                    occurrences = []
                    search_pos = 0
                    for _ in range(count):
                        pos = original.find(old_content, search_pos)
                        if pos == -1:
                            break
                        line_num = original[:pos].count("\n") + 1
                        occurrences.append(line_num)
                        search_pos = pos + 1

                    locations = ", ".join(f"line {n}" for n in occurrences)
                    error = (
                        f"Content appears {count} times at {locations}. "
                        "Provide more surrounding context in old_content to uniquely "
                        "identify which occurrence to edit."
                    )
                    if operation:
                        operation.mark_failed(error)
                    return EditResult(
                        success=False,
                        file_path=str(path),
                        lines_added=0,
                        lines_removed=0,
                        error=error,
                        operation_id=operation.id if operation else None,
                    )

                # Perform replacement
                if match_all:
                    modified = original.replace(old_content, new_content)
                else:
                    modified = original.replace(old_content, new_content, 1)

                # Calculate diff statistics and textual diff
                diff = Diff(str(path), original, modified)
                stats = diff.get_stats()
                diff_text = diff.generate_unified_diff(context_lines=3)

                # Dry run - don't actually write
                if dry_run:
                    return EditResult(
                        success=True,
                        file_path=str(path),
                        lines_added=stats["lines_added"],
                        lines_removed=stats["lines_removed"],
                        diff=diff_text,
                        operation_id=operation.id if operation else None,
                    )

                # Mark operation as executing
                if operation:
                    operation.mark_executing()

                # Create backup if requested
                backup_path = None
                if backup and self.config.operation.backup_before_edit:
                    backup_path = str(path) + ".bak"
                    shutil.copy2(path, backup_path)

                # Write modified content
                with open(path, "w", encoding="utf-8") as f:
                    f.write(modified)

                # Mark operation as successful
                if operation:
                    operation.mark_success()

                return EditResult(
                    success=True,
                    file_path=str(path),
                    lines_added=stats["lines_added"],
                    lines_removed=stats["lines_removed"],
                    backup_path=backup_path,
                    diff=diff_text,
                    operation_id=operation.id if operation else None,
                )

        except Exception as e:
            error = f"Failed to edit file: {str(e)}"
            if operation:
                operation.mark_failed(error)
            return EditResult(
                success=False,
                file_path=str(path),
                lines_added=0,
                lines_removed=0,
                error=error,
                operation_id=operation.id if operation else None,
            )

    def edit_lines(
        self,
        file_path: str,
        line_start: int,
        line_end: int,
        new_content: str,
        dry_run: bool = False,
        backup: bool = True,
        operation: Optional[Operation] = None,
    ) -> EditResult:
        """Edit specific lines in a file.

        Args:
            file_path: Path to file
            line_start: Starting line (1-indexed, inclusive)
            line_end: Ending line (1-indexed, inclusive)
            new_content: New content for those lines
            dry_run: If True, don't actually modify file
            backup: Create backup before editing
            operation: Operation object for tracking

        Returns:
            EditResult with operation details
        """
        path = self._resolve_path(file_path)

        # Check if file exists
        if not path.exists():
            error = f"File not found: {path}"
            if operation:
                operation.mark_failed(error)
            return EditResult(
                success=False,
                file_path=str(path),
                lines_added=0,
                lines_removed=0,
                error=error,
                operation_id=operation.id if operation else None,
            )

        try:
            # Read file
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Validate line numbers
            if line_start < 1 or line_end > len(lines) or line_start > line_end:
                error = (
                    f"Invalid line range: {line_start}-{line_end} "
                    f"(file has {len(lines)} lines)"
                )
                if operation:
                    operation.mark_failed(error)
                return EditResult(
                    success=False,
                    file_path=str(path),
                    lines_added=0,
                    lines_removed=0,
                    error=error,
                    operation_id=operation.id if operation else None,
                )

            # Build old and new content
            original = "".join(lines)
            old_lines = lines[line_start - 1 : line_end]
            old_content = "".join(old_lines)

            # Replace lines
            new_lines = (
                lines[: line_start - 1]
                + [new_content if not new_content.endswith("\n") else new_content]
                + lines[line_end:]
            )

            if not new_content.endswith("\n") and line_end < len(lines):
                new_lines[line_start - 1] += "\n"

            modified = "".join(new_lines)

            # Use the main edit_file method
            return self.edit_file(
                file_path=file_path,
                old_content=old_content,
                new_content=new_content if new_content.endswith("\n") else new_content + "\n",
                match_all=False,
                dry_run=dry_run,
                backup=backup,
                operation=operation,
            )

        except Exception as e:
            error = f"Failed to edit lines: {str(e)}"
            if operation:
                operation.mark_failed(error)
            return EditResult(
                success=False,
                file_path=str(path),
                lines_added=0,
                lines_removed=0,
                error=error,
                operation_id=operation.id if operation else None,
            )

    def execute(self, **kwargs) -> EditResult:
        """Execute the tool.

        Args:
            **kwargs: Arguments for edit_file

        Returns:
            EditResult
        """
        return self.edit_file(**kwargs)

    def preview_edit(self, file_path: str, old_content: str, new_content: str) -> None:
        """Preview an edit operation.

        Args:
            file_path: Path to file
            old_content: Content to replace
            new_content: New content
        """
        path = self._resolve_path(file_path)

        # Read original
        with open(path, "r", encoding="utf-8") as f:
            original = f.read()

        # Generate modified
        modified = original.replace(old_content, new_content, 1)

        # Display diff
        self.diff_preview.preview_edit(str(path), original, modified)

    def _resolve_path(self, path: str) -> Path:
        """Resolve a path relative to working directory.

        Args:
            path: Path string (relative or absolute)

        Returns:
            Resolved Path object
        """
        p = Path(path).expanduser()
        if p.is_absolute():
            return p
        return (self.working_dir / p).resolve()
