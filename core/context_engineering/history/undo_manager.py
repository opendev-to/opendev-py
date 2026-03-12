"""Undo system for rolling back operations."""

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from opendev.models.operation import Operation, OperationType

logger = logging.getLogger(__name__)


class UndoResult:
    """Result of an undo operation."""

    def __init__(
        self,
        success: bool,
        operation_id: str,
        error: Optional[str] = None,
    ):
        """Initialize undo result.

        Args:
            success: Whether undo was successful
            operation_id: ID of operation that was undone
            error: Error message if failed
        """
        self.success = success
        self.operation_id = operation_id
        self.error = error


class UndoManager:
    """Manager for undoing operations."""

    def __init__(self, max_history: int = 50, session_dir: Optional[Path] = None):
        """Initialize undo manager.

        Args:
            max_history: Maximum number of operations to track
            session_dir: Directory for persistent operation log (JSONL)
        """
        self.max_history = max_history
        self.history: list[Operation] = []
        self._session_dir = session_dir

    def record_operation(self, operation: Operation) -> None:
        """Record an operation for potential undo.

        Also appends to the persistent JSONL log if session_dir is set.

        Args:
            operation: Operation to record
        """
        self.history.append(operation)

        # Trim history if needed
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]

        # Persist to JSONL
        self._append_to_log(operation)

    def _append_to_log(self, operation: Operation) -> None:
        """Append an operation to the persistent JSONL log file.

        Args:
            operation: Operation to persist
        """
        if not self._session_dir:
            return

        try:
            self._session_dir.mkdir(parents=True, exist_ok=True)
            log_file = self._session_dir / "operations.jsonl"
            record = {
                "timestamp": operation.created_at.isoformat(),
                "type": operation.type.value,
                "path": operation.target,
                "status": operation.status.value,
                "id": operation.id,
            }
            with open(log_file, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass  # Don't let logging failures break operations

    @staticmethod
    def load_operations(session_dir: Path) -> list[dict]:
        """Load operations from the persistent JSONL log.

        Args:
            session_dir: Directory containing operations.jsonl

        Returns:
            List of operation dicts from the log
        """
        log_file = session_dir / "operations.jsonl"
        if not log_file.exists():
            return []

        operations = []
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        operations.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return operations

    def undo_last(self) -> UndoResult:
        """Undo the last operation.

        Returns:
            UndoResult with details
        """
        if not self.history:
            return UndoResult(
                success=False,
                operation_id="",
                error="No operations to undo",
            )

        operation = self.history.pop()
        return self.undo_operation(operation)

    def undo_operation(self, operation: Operation) -> UndoResult:
        """Undo a specific operation.

        Args:
            operation: Operation to undo

        Returns:
            UndoResult with details
        """
        try:
            if operation.type == OperationType.FILE_WRITE:
                return self._undo_file_write(operation)
            elif operation.type == OperationType.FILE_EDIT:
                return self._undo_file_edit(operation)
            elif operation.type == OperationType.FILE_DELETE:
                return self._undo_file_delete(operation)
            else:
                return UndoResult(
                    success=False,
                    operation_id=operation.id,
                    error=f"Cannot undo operation type: {operation.type}",
                )
        except Exception as e:
            return UndoResult(
                success=False,
                operation_id=operation.id,
                error=f"Undo failed: {str(e)}",
            )

    def _undo_file_write(self, operation: Operation) -> UndoResult:
        """Undo a file write operation.

        Args:
            operation: File write operation

        Returns:
            UndoResult
        """
        file_path = Path(operation.target)

        # Delete the created file
        if file_path.exists():
            file_path.unlink()
            return UndoResult(
                success=True,
                operation_id=operation.id,
            )
        else:
            return UndoResult(
                success=False,
                operation_id=operation.id,
                error=f"File not found: {file_path}",
            )

    def _undo_file_edit(self, operation: Operation) -> UndoResult:
        """Undo a file edit operation.

        Args:
            operation: File edit operation

        Returns:
            UndoResult
        """
        file_path = Path(operation.target)
        backup_path = operation.parameters.get("backup_path")

        if not backup_path:
            return UndoResult(
                success=False,
                operation_id=operation.id,
                error="No backup found for this edit",
            )

        backup = Path(backup_path)
        if not backup.exists():
            return UndoResult(
                success=False,
                operation_id=operation.id,
                error=f"Backup file not found: {backup}",
            )

        # Restore from backup
        shutil.copy2(backup, file_path)

        return UndoResult(
            success=True,
            operation_id=operation.id,
        )

    def _undo_file_delete(self, operation: Operation) -> UndoResult:
        """Undo a file delete operation.

        Args:
            operation: File delete operation

        Returns:
            UndoResult
        """
        # Check if we have a backup
        backup_path = operation.parameters.get("backup_path")

        if not backup_path:
            return UndoResult(
                success=False,
                operation_id=operation.id,
                error="No backup found for deleted file",
            )

        backup = Path(backup_path)
        file_path = Path(operation.target)

        if not backup.exists():
            return UndoResult(
                success=False,
                operation_id=operation.id,
                error=f"Backup file not found: {backup}",
            )

        # Restore file
        shutil.copy2(backup, file_path)

        return UndoResult(
            success=True,
            operation_id=operation.id,
        )

    def list_history(self, limit: int = 10) -> list[Operation]:
        """List recent operations that can be undone.

        Args:
            limit: Maximum number to return

        Returns:
            List of operations (most recent first)
        """
        return list(reversed(self.history[-limit:]))

    def clear_history(self) -> None:
        """Clear all operation history."""
        self.history.clear()

    def get_history_size(self) -> int:
        """Get number of operations in history."""
        return len(self.history)

    def get_revert_preview(self, count: int = 1) -> str:
        """Get a preview of what the last N undo operations would revert.

        Args:
            count: Number of recent operations to preview.

        Returns:
            Human-readable diff summary.
        """
        if not self.history:
            return "No operations to undo."

        ops = self.history[-count:]
        lines = [f"Would revert {len(ops)} operation(s):"]
        for op in reversed(ops):
            op_type = op.type.value if hasattr(op.type, "value") else str(op.type)
            target = op.target or "unknown"
            lines.append(f"  - {op_type}: {target}")
        return "\n".join(lines)

    def revert_with_snapshot(self, snapshot_id: str, project_dir: Path) -> list[str]:
        """Revert file changes using the SnapshotManager.

        Delegates to the snapshot system to restore files from a previous
        snapshot, providing reliable per-message revert.

        Args:
            snapshot_id: The snapshot commit/tree hash to revert to.
            project_dir: The project directory for the SnapshotManager.

        Returns:
            List of file paths that were reverted.
        """
        from opendev.core.snapshot.manager import SnapshotManager

        try:
            snapshot_mgr = SnapshotManager(project_dir)
            reverted = snapshot_mgr.revert_to_snapshot(snapshot_id)
            if reverted:
                logger.info(
                    "Reverted %d file(s) using snapshot %s",
                    len(reverted),
                    snapshot_id[:8],
                )
            return reverted
        except Exception:
            logger.warning("Failed to revert with snapshot %s", snapshot_id, exc_info=True)
            return []

    def get_changes_summary(self) -> dict:
        """Get summary stats of all operations in history.

        Returns:
            Dict with total_operations, unique_files, and by_type breakdown.
        """
        files: set[str] = set()
        op_types: dict[str, int] = {}
        for op in self.history:
            if op.target:
                files.add(op.target)
            op_type = op.type.value if hasattr(op.type, "value") else str(op.type)
            op_types[op_type] = op_types.get(op_type, 0) + 1
        return {
            "total_operations": len(self.history),
            "unique_files": len(files),
            "by_type": op_types,
        }
