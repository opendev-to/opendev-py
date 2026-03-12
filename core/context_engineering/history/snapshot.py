"""Shadow git snapshot system for per-step undo.

Maintains a parallel shadow git repository at ~/.opendev/snapshot/<project_id>/
that captures a tree hash at every agent step, enabling perfect per-step
undo/revert without touching the user's real git repo.

Key operations:
- track(): Capture current workspace state as a tree hash
- patch(hash): Get list of files changed since a snapshot
- revert(hash, files): Restore specific files from a snapshot
- restore(hash): Full restoration to a snapshot state
- undo_last(): Convenience method to revert to the previous snapshot

Uses git's content-addressable storage for efficient deduplication.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def _encode_project_id(project_path: str) -> str:
    """Create a stable, filesystem-safe ID from a project path."""
    return hashlib.sha256(project_path.encode()).hexdigest()[:16]


class SnapshotManager:
    """Manages shadow git snapshots for per-step undo.

    Each snapshot is a git tree hash that captures the complete state
    of the workspace at that point in time.
    """

    def __init__(self, project_dir: str) -> None:
        """Initialize snapshot manager for a project.

        Args:
            project_dir: Absolute path to the project directory.
        """
        self._project_dir = os.path.abspath(project_dir)
        self._project_id = _encode_project_id(self._project_dir)
        self._shadow_dir = Path.home() / ".opendev" / "snapshot" / self._project_id
        self._snapshots: list[str] = []  # Stack of tree hashes (most recent last)
        self._initialized = False

    @property
    def shadow_git_dir(self) -> Path:
        """Path to the shadow .git directory."""
        return self._shadow_dir

    def _ensure_initialized(self) -> bool:
        """Ensure the shadow git repo exists and is initialized.

        Returns:
            True if initialized successfully, False otherwise.
        """
        if self._initialized:
            return True

        try:
            self._shadow_dir.mkdir(parents=True, exist_ok=True)

            # Check if already a git repo
            if (self._shadow_dir / "HEAD").exists():
                self._sync_gitignore()
                self._initialized = True
                return True

            # Initialize bare-ish shadow repo
            self._git("init", "--bare")
            self._sync_gitignore()
            self._initialized = True
            logger.info("Shadow snapshot repo initialized at %s", self._shadow_dir)
            return True
        except Exception:
            logger.warning("Failed to initialize shadow snapshot repo", exc_info=True)
            return False

    def _sync_gitignore(self) -> None:
        """Sync .gitignore and info/exclude from the real repo."""
        # Copy .gitignore patterns to shadow's info/exclude
        real_gitignore = Path(self._project_dir) / ".gitignore"
        shadow_exclude = self._shadow_dir / "info" / "exclude"

        try:
            shadow_exclude.parent.mkdir(parents=True, exist_ok=True)
            patterns = []

            if real_gitignore.exists():
                patterns.append(real_gitignore.read_text(encoding="utf-8"))

            # Also read from real repo's info/exclude
            real_exclude = Path(self._project_dir) / ".git" / "info" / "exclude"
            if real_exclude.exists():
                patterns.append(real_exclude.read_text(encoding="utf-8"))

            # Always exclude common patterns
            patterns.append(
                "\n# Shadow snapshot defaults\n"
                ".git\n"
                "node_modules\n"
                "__pycache__\n"
                "*.pyc\n"
                ".venv\n"
                "venv\n"
            )

            shadow_exclude.write_text("\n".join(patterns), encoding="utf-8")
        except OSError:
            pass  # Best-effort

    def track(self) -> Optional[str]:
        """Capture current workspace state as a tree hash.

        Runs `git add . && git write-tree` in the shadow repo to create
        a content-addressable snapshot of the current state.

        Returns:
            Tree hash string, or None if tracking failed.
        """
        if not self._ensure_initialized():
            return None

        try:
            # Stage all files from the working directory
            self._git(
                "--work-tree",
                self._project_dir,
                "add",
                "--all",
                "--force",
            )

            # Write the index as a tree object
            tree_hash = self._git(
                "write-tree",
            ).strip()

            if tree_hash:
                self._snapshots.append(tree_hash)
                logger.debug(
                    "Snapshot captured: %s (total: %d)", tree_hash[:8], len(self._snapshots)
                )
                return tree_hash

        except Exception:
            logger.debug("Failed to capture snapshot", exc_info=True)

        return None

    def patch(self, tree_hash: str) -> List[str]:
        """Get list of files that changed since a snapshot.

        Args:
            tree_hash: Tree hash from a previous track() call.

        Returns:
            List of file paths that differ between the snapshot and current state.
        """
        if not self._ensure_initialized():
            return []

        try:
            # First capture current state
            current_hash = self.track()
            if not current_hash:
                return []

            # Diff the two trees
            output = self._git(
                "diff-tree",
                "-r",
                "--name-only",
                tree_hash,
                current_hash,
            )
            return [line for line in output.strip().splitlines() if line]

        except Exception:
            logger.debug("Failed to compute patch", exc_info=True)
            return []

    def revert(self, tree_hash: str, files: Optional[List[str]] = None) -> List[str]:
        """Restore specific files (or all) from a snapshot.

        Args:
            tree_hash: Tree hash to restore from.
            files: Specific files to restore. If None, restores all changed files.

        Returns:
            List of files that were restored.
        """
        if not self._ensure_initialized():
            return []

        try:
            if files is None:
                files = self.patch(tree_hash)

            if not files:
                return []

            restored = []
            for filepath in files:
                try:
                    self._git(
                        "--work-tree",
                        self._project_dir,
                        "checkout",
                        tree_hash,
                        "--",
                        filepath,
                    )
                    restored.append(filepath)
                except Exception:
                    logger.debug("Failed to restore %s from %s", filepath, tree_hash[:8])

            logger.info("Restored %d files from snapshot %s", len(restored), tree_hash[:8])
            return restored

        except Exception:
            logger.warning("Failed to revert from snapshot", exc_info=True)
            return []

    def restore(self, tree_hash: str) -> bool:
        """Full restoration to a snapshot state.

        Uses read-tree + checkout-index for atomic restoration.

        Args:
            tree_hash: Tree hash to restore to.

        Returns:
            True if restoration was successful.
        """
        if not self._ensure_initialized():
            return False

        try:
            # Read the tree into the index
            self._git("read-tree", tree_hash)

            # Checkout all files from the index to the working directory
            self._git(
                "--work-tree",
                self._project_dir,
                "checkout-index",
                "--all",
                "--force",
            )

            logger.info("Fully restored workspace to snapshot %s", tree_hash[:8])
            return True

        except Exception:
            logger.warning("Failed to restore snapshot", exc_info=True)
            return False

    def undo_last(self) -> Optional[str]:
        """Convenience: revert to the snapshot before the most recent one.

        Returns:
            Description of what was undone, or None if nothing to undo.
        """
        if len(self._snapshots) < 2:
            return None

        # Pop the current snapshot (most recent)
        self._snapshots.pop()

        # Get the previous snapshot to restore to
        target_hash = self._snapshots[-1]

        # Get changed files first for the description
        changed = self.patch(target_hash)
        if not changed:
            return None

        if self.restore(target_hash):
            desc = f"Reverted {len(changed)} file(s) to previous state"
            if len(changed) <= 5:
                desc += ": " + ", ".join(changed)
            return desc

        return None

    def get_snapshot_count(self) -> int:
        """Return number of snapshots recorded this session."""
        return len(self._snapshots)

    def cleanup(self) -> None:
        """Run git gc on the shadow repo to free space."""
        if not self._initialized:
            return
        try:
            self._git("gc", "--prune=7.days.ago", "--quiet")
        except Exception:
            pass

    def _git(self, *args: str) -> str:
        """Run a git command against the shadow repo.

        Returns:
            stdout as string.

        Raises:
            subprocess.CalledProcessError on failure.
        """
        cmd = ["git", "--git-dir", str(self._shadow_dir), *args]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=self._project_dir,
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() or f"git command failed: {' '.join(args)}"
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
        return result.stdout
