"""Apply unified diff patches to files."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PatchTool:
    """Apply unified diff patches to one or more files."""

    def __init__(self, working_dir: Optional[str] = None) -> None:
        self._cwd = working_dir or os.getcwd()

    def apply_patch(
        self,
        patch: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Apply a unified diff patch.

        Args:
            patch: Unified diff string (output of `git diff` or `diff -u`)
            dry_run: If True, validate without applying

        Returns:
            Result dict with files modified
        """
        if not patch or not patch.strip():
            return {"success": False, "error": "Patch content is required", "output": None}

        # Validate patch format
        if not any(line.startswith(("---", "diff --git")) for line in patch.split("\n")):
            return {
                "success": False,
                "error": "Invalid patch format. Expected unified diff (--- / +++ / @@ headers).",
                "output": None,
            }

        # Extract files that will be modified
        files = self._extract_files(patch)

        # Write patch to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False, dir=self._cwd
        ) as f:
            f.write(patch)
            patch_file = f.name

        try:
            # Try git apply first (handles git-style patches better)
            args = ["git", "apply"]
            if dry_run:
                args.append("--check")
            args.append(patch_file)

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                cwd=self._cwd,
                timeout=30,
            )

            if result.returncode == 0:
                action = "validated" if dry_run else "applied"
                return {
                    "success": True,
                    "output": (
                        f"Patch {action} successfully. "
                        f"Files: {', '.join(files) or 'unknown'}"
                    ),
                    "files": files,
                }
            else:
                # Try standard patch command as fallback
                args2 = ["patch", "-p1"]
                if dry_run:
                    args2.append("--dry-run")
                args2.extend(["-i", patch_file])

                result2 = subprocess.run(
                    args2,
                    capture_output=True,
                    text=True,
                    cwd=self._cwd,
                    timeout=30,
                )

                if result2.returncode == 0:
                    action = "validated" if dry_run else "applied"
                    return {
                        "success": True,
                        "output": (
                            f"Patch {action} successfully (via patch). "
                            f"Files: {', '.join(files) or 'unknown'}"
                        ),
                        "files": files,
                    }
                else:
                    error = result.stderr.strip() or result2.stderr.strip()
                    return {
                        "success": False,
                        "error": f"Patch failed: {error}",
                        "output": None,
                    }
        finally:
            # Clean up temp file
            try:
                os.unlink(patch_file)
            except OSError:
                pass

    @staticmethod
    def _extract_files(patch: str) -> list[str]:
        """Extract file paths from a unified diff."""
        files = []
        for line in patch.split("\n"):
            # git diff format
            m = re.match(r'^diff --git a/(.*?) b/(.*?)$', line)
            if m:
                files.append(m.group(2))
                continue
            # Standard diff format
            m = re.match(r'^\+\+\+ b?/(.*?)$', line)
            if m:
                path = m.group(1)
                if path and path != "/dev/null":
                    files.append(path)
        return list(dict.fromkeys(files))  # Deduplicate preserving order
