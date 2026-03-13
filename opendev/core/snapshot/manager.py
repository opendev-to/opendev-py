"""Git-based snapshot system for reliable file change tracking and revert.

Uses a shadow git repository to create atomic snapshots of modified files
before and after tool execution. This enables reliable revert of any
change set, regardless of complexity.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SnapshotManager:
    """Manages file snapshots using a shadow git repository."""

    def __init__(self, project_dir: Path):
        self._project_dir = project_dir.resolve()
        self._project_id = self._compute_project_id()
        self._snapshot_dir = (
            Path.home() / ".opendev" / "data" / "snapshot" / self._project_id
        )
        self._initialized = False
        self._current_snapshot_id: str | None = None

    def _compute_project_id(self) -> str:
        """Compute a stable project identifier from the project path."""
        return hashlib.sha256(str(self._project_dir).encode()).hexdigest()[:16]

    @property
    def snapshot_dir(self) -> Path:
        return self._snapshot_dir

    def _ensure_initialized(self) -> bool:
        """Initialize the shadow git repo if needed."""
        if self._initialized:
            return True
        try:
            self._snapshot_dir.mkdir(parents=True, exist_ok=True)
            git_dir = self._snapshot_dir / ".git"
            if not git_dir.exists():
                self._git("init")
                # Configure for snapshot use
                self._git("config", "user.name", "opendev-snapshot")
                self._git("config", "user.email", "snapshot@opendev.local")
                self._git("config", "gc.auto", "0")  # Manual GC only
            self._initialized = True
            return True
        except Exception:
            logger.warning("Failed to initialize snapshot repo", exc_info=True)
            return False

    def take_snapshot(self, files: list[str], label: str = "") -> str | None:
        """Take a snapshot of the given files before modification.

        Args:
            files: List of absolute file paths to snapshot.
            label: Human-readable label for the snapshot.

        Returns:
            Snapshot ID (git commit hash) or None on failure.
        """
        if not self._ensure_initialized():
            return None

        try:
            # Copy files into snapshot repo
            copied = 0
            for file_path in files:
                src = Path(file_path)
                if not src.exists():
                    continue
                # Compute relative path from project root
                try:
                    rel = src.relative_to(self._project_dir)
                except ValueError:
                    rel = Path(src.name)
                dest = self._snapshot_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(src.read_bytes())
                self._git("add", str(rel))
                copied += 1

            if copied == 0:
                return None

            # Commit snapshot
            msg = f"snapshot: {label}" if label else "snapshot"
            self._git("commit", "-m", msg, "--allow-empty")

            # Get commit hash
            result = self._git("rev-parse", "HEAD")
            snapshot_id = result.strip() if result else None
            self._current_snapshot_id = snapshot_id

            logger.debug(
                "Snapshot %s: %d files (%s)",
                snapshot_id[:8] if snapshot_id else "?",
                copied,
                label,
            )
            return snapshot_id

        except Exception:
            logger.warning("Failed to take snapshot", exc_info=True)
            return None

    def get_diff(self, snapshot_id: str) -> str | None:
        """Get diff between a snapshot and the current project state.

        Args:
            snapshot_id: The snapshot commit hash to diff against.

        Returns:
            Unified diff string or None.
        """
        if not self._ensure_initialized():
            return None

        try:
            # Copy current versions of snapshotted files
            result = self._git("diff-tree", "--no-commit-id", "-r", "--name-only", snapshot_id)
            if not result:
                return None

            files = result.strip().split("\n")
            for rel_path in files:
                if not rel_path.strip():
                    continue
                src = self._project_dir / rel_path
                dest = self._snapshot_dir / rel_path
                if src.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(src.read_bytes())
                elif dest.exists():
                    dest.unlink()

            # Generate diff
            diff = self._git("diff", snapshot_id, "--")
            return diff

        except Exception:
            logger.warning("Failed to get diff", exc_info=True)
            return None

    def revert_to_snapshot(self, snapshot_id: str) -> list[str]:
        """Revert project files to a snapshot state.

        Args:
            snapshot_id: The snapshot commit hash to revert to.

        Returns:
            List of reverted file paths.
        """
        if not self._ensure_initialized():
            return []

        try:
            # Get files from snapshot
            result = self._git("diff-tree", "--no-commit-id", "-r", "--name-only", snapshot_id)
            if not result:
                return []

            reverted = []
            files = result.strip().split("\n")
            for rel_path in files:
                if not rel_path.strip():
                    continue
                # Checkout file from snapshot into snapshot dir
                self._git("checkout", snapshot_id, "--", rel_path)
                # Copy back to project
                src = self._snapshot_dir / rel_path
                dest = self._project_dir / rel_path
                if src.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(src.read_bytes())
                    reverted.append(str(dest))

            return reverted

        except Exception:
            logger.warning("Failed to revert to snapshot", exc_info=True)
            return []

    def cleanup(self, max_age_days: int = 7) -> None:
        """Run garbage collection on the snapshot repo."""
        if not self._ensure_initialized():
            return
        try:
            self._git("gc", f"--prune={max_age_days}.days.ago")
        except Exception:
            logger.debug("Snapshot GC failed", exc_info=True)

    def _git(self, *args: str) -> str | None:
        """Run a git command in the snapshot directory."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=str(self._snapshot_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0 and "nothing to commit" not in result.stderr:
                logger.debug("git %s failed: %s", " ".join(args), result.stderr.strip())
                return None
            return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
