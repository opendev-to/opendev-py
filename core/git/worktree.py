"""Git worktree management for isolated experiments."""

from __future__ import annotations

import logging
import random
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Adjective-noun naming for worktrees
_ADJECTIVES = [
    "swift",
    "bright",
    "calm",
    "bold",
    "keen",
    "warm",
    "cool",
    "deep",
    "fair",
    "fine",
    "glad",
    "pure",
    "safe",
    "wise",
    "neat",
]
_NOUNS = [
    "branch",
    "patch",
    "spike",
    "draft",
    "build",
    "probe",
    "trial",
    "craft",
    "forge",
    "bloom",
    "spark",
    "quest",
    "grove",
    "ridge",
    "haven",
]


def _random_name() -> str:
    """Generate a random adjective-noun worktree name."""
    return f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}"


class WorktreeInfo:
    """Information about a git worktree."""

    def __init__(self, path: str, branch: str, commit: str, is_main: bool = False):
        self.path = path
        self.branch = branch
        self.commit = commit
        self.is_main = is_main

    def __repr__(self) -> str:
        main = " (main)" if self.is_main else ""
        return f"Worktree({self.branch}{main}, {self.path})"


class WorktreeManager:
    """Manages git worktrees for the current project."""

    def __init__(self, project_dir: Path):
        self._project_dir = project_dir.resolve()
        self._worktree_base = Path.home() / ".opendev" / "data" / "worktree"

    def create(
        self,
        name: Optional[str] = None,
        branch: Optional[str] = None,
        base_branch: str = "HEAD",
    ) -> WorktreeInfo | None:
        """Create a new worktree.

        Args:
            name: Worktree name (auto-generated if None).
            branch: Branch name for the worktree (defaults to worktree-{name}).
            base_branch: Base branch/commit to branch from.

        Returns:
            WorktreeInfo or None on failure.
        """
        name = name or _random_name()
        branch = branch or f"worktree-{name}"
        worktree_path = self._worktree_base / name

        try:
            worktree_path.parent.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                ["git", "worktree", "add", "-b", branch, str(worktree_path), base_branch],
                cwd=str(self._project_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.warning("Failed to create worktree: %s", result.stderr.strip())
                return None

            commit = self._git("rev-parse", "HEAD", cwd=str(worktree_path))
            return WorktreeInfo(
                path=str(worktree_path),
                branch=branch,
                commit=commit.strip() if commit else "",
            )

        except Exception:
            logger.warning("Failed to create worktree", exc_info=True)
            return None

    def list(self) -> list[WorktreeInfo]:
        """List all worktrees for the project."""
        result = self._git("worktree", "list", "--porcelain")
        if not result:
            return []

        worktrees = []
        current: dict = {}
        for line in result.split("\n"):
            if line.startswith("worktree "):
                if current:
                    worktrees.append(self._parse_worktree(current))
                current = {"path": line[9:]}
            elif line.startswith("HEAD "):
                current["commit"] = line[5:]
            elif line.startswith("branch "):
                current["branch"] = line[7:].replace("refs/heads/", "")
            elif line == "bare":
                current["is_main"] = True

        if current:
            worktrees.append(self._parse_worktree(current))

        return worktrees

    def remove(self, name: str, force: bool = False) -> bool:
        """Remove a worktree.

        Args:
            name: Worktree name or path.
            force: Force removal even if there are changes.

        Returns:
            True if removed successfully.
        """
        worktree_path = self._worktree_base / name
        if not worktree_path.exists():
            # Try treating as absolute path
            worktree_path = Path(name)

        cmd = ["git", "worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(worktree_path))

        result = subprocess.run(
            cmd,
            cwd=str(self._project_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.warning("Failed to remove worktree: %s", result.stderr.strip())
            return False

        return True

    def reset(self, name: str) -> bool:
        """Reset a worktree to its branch HEAD.

        Args:
            name: Worktree name.

        Returns:
            True if reset successfully.
        """
        worktree_path = self._worktree_base / name
        if not worktree_path.exists():
            return False

        result = self._git("reset", "--hard", "HEAD", cwd=str(worktree_path))
        return result is not None

    @staticmethod
    def _parse_worktree(data: dict) -> WorktreeInfo:
        return WorktreeInfo(
            path=data.get("path", ""),
            branch=data.get("branch", "detached"),
            commit=data.get("commit", ""),
            is_main=data.get("is_main", False),
        )

    def _git(self, *args: str, cwd: str | None = None) -> str | None:
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=cwd or str(self._project_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None
            return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
