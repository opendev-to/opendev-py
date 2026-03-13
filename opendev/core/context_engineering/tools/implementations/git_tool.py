"""Structured git operations with safety checks."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Branches that should never be force-pushed to
PROTECTED_BRANCHES = {"main", "master", "develop", "production", "staging"}


def _run_git(args: list[str], cwd: Optional[str] = None, timeout: int = 30) -> tuple[bool, str]:
    """Run a git command and return (success, output)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            error = result.stderr.strip() or output
            return False, error
        return True, output
    except subprocess.TimeoutExpired:
        return False, f"Git command timed out after {timeout}s"
    except FileNotFoundError:
        return False, "git is not installed or not in PATH"


class GitTool:
    """Structured git operations with safety checks."""

    def __init__(self, working_dir: Optional[str] = None) -> None:
        self._cwd = working_dir or os.getcwd()

    def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        """Dispatch to the appropriate git action."""
        actions = {
            "status": self._status,
            "diff": self._diff,
            "log": self._log,
            "branch": self._branch,
            "checkout": self._checkout,
            "commit": self._commit,
            "push": self._push,
            "pull": self._pull,
            "stash": self._stash,
            "merge": self._merge,
            "create_pr": self._create_pr,
        }
        handler = actions.get(action)
        if not handler:
            return {
                "success": False,
                "error": f"Unknown git action: {action}. Available: {', '.join(actions.keys())}",
                "output": None,
            }
        return handler(**kwargs)

    def _status(self, **kwargs: Any) -> dict[str, Any]:
        """Get structured git status."""
        ok, out = _run_git(["status", "--porcelain=v1", "-b"], cwd=self._cwd)
        if not ok:
            return {"success": False, "error": out, "output": None}

        lines = out.split("\n") if out else []
        branch_line = lines[0] if lines and lines[0].startswith("##") else ""
        branch = branch_line.replace("## ", "").split("...")[0] if branch_line else "unknown"

        changes = []
        for line in lines[1:]:
            if len(line) >= 3:
                status_code = line[:2]
                file_path = line[3:]
                changes.append({"status": status_code.strip(), "file": file_path})

        # Also get ahead/behind info
        ahead = behind = 0
        if "ahead" in branch_line:
            m = re.search(r'ahead (\d+)', branch_line)
            if m:
                ahead = int(m.group(1))
        if "behind" in branch_line:
            m = re.search(r'behind (\d+)', branch_line)
            if m:
                behind = int(m.group(1))

        output_parts = [f"Branch: {branch}"]
        if ahead:
            output_parts.append(f"Ahead: {ahead} commits")
        if behind:
            output_parts.append(f"Behind: {behind} commits")
        if changes:
            output_parts.append(f"\nChanges ({len(changes)}):")
            for c in changes[:50]:
                output_parts.append(f"  {c['status']} {c['file']}")
            if len(changes) > 50:
                output_parts.append(f"  ... and {len(changes) - 50} more")
        else:
            output_parts.append("Working tree clean")

        return {
            "success": True,
            "output": "\n".join(output_parts),
            "branch": branch,
            "changes": changes,
            "ahead": ahead,
            "behind": behind,
        }

    def _diff(
        self, file: Optional[str] = None, staged: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        """Get diff output."""
        args = ["diff"]
        if staged:
            args.append("--cached")
        args.append("--stat")
        if file:
            args.extend(["--", file])

        ok, stat_out = _run_git(args, cwd=self._cwd)
        if not ok:
            return {"success": False, "error": stat_out, "output": None}

        # Also get the actual diff (limited)
        detail_args = ["diff"]
        if staged:
            detail_args.append("--cached")
        if file:
            detail_args.extend(["--", file])

        ok2, diff_out = _run_git(detail_args, cwd=self._cwd)
        output = stat_out
        if ok2 and diff_out:
            output += "\n\n" + diff_out

        return {"success": True, "output": output or "No differences found"}

    def _log(self, limit: int = 10, oneline: bool = True, **kwargs: Any) -> dict[str, Any]:
        """Get git log."""
        args = ["log", f"-{limit}"]
        if oneline:
            args.append("--format=%h %s (%cr) <%an>")
        else:
            args.append("--format=%H%n%s%n%b%n---")

        ok, out = _run_git(args, cwd=self._cwd)
        if not ok:
            return {"success": False, "error": out, "output": None}

        return {"success": True, "output": out or "No commits found"}

    def _branch(
        self, name: Optional[str] = None, delete: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        """List or create branches."""
        if name and delete:
            ok, out = _run_git(["branch", "-d", name], cwd=self._cwd)
            return {
                "success": ok,
                "output": out if ok else None,
                "error": out if not ok else None,
            }
        elif name:
            ok, out = _run_git(["branch", name], cwd=self._cwd)
            return {
                "success": ok,
                "output": f"Created branch: {name}" if ok else None,
                "error": out if not ok else None,
            }
        else:
            ok, out = _run_git(
                ["branch", "-a", "--format=%(refname:short) %(upstream:short) %(objectname:short)"],
                cwd=self._cwd,
            )
            if not ok:
                return {"success": False, "error": out, "output": None}
            return {"success": True, "output": out}

    def _checkout(
        self, branch: str = "", create: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        """Checkout a branch."""
        if not branch:
            return {"success": False, "error": "Branch name is required", "output": None}

        # Safety: warn about uncommitted changes
        ok, status_out = _run_git(["status", "--porcelain"], cwd=self._cwd)
        if ok and status_out.strip():
            dirty_count = len([ln for ln in status_out.strip().split("\n") if ln.strip()])
            if dirty_count > 0:
                return {
                    "success": False,
                    "error": (
                        f"Working tree has {dirty_count} uncommitted changes. "
                        "Commit or stash them first."
                    ),
                    "output": None,
                }

        args = ["checkout"]
        if create:
            args.append("-b")
        args.append(branch)

        ok, out = _run_git(args, cwd=self._cwd)
        return {
            "success": ok,
            "output": f"Switched to branch: {branch}" if ok else None,
            "error": out if not ok else None,
        }

    def _commit(self, message: str = "", **kwargs: Any) -> dict[str, Any]:
        """Create a commit."""
        if not message:
            return {"success": False, "error": "Commit message is required", "output": None}

        # Check if there are staged changes
        ok, staged = _run_git(["diff", "--cached", "--stat"], cwd=self._cwd)
        if ok and not staged.strip():
            return {
                "success": False,
                "error": "No staged changes to commit. Use 'git add' first.",
                "output": None,
            }

        ok, out = _run_git(["commit", "-m", message], cwd=self._cwd)
        return {
            "success": ok,
            "output": out if ok else None,
            "error": out if not ok else None,
        }

    def _push(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        force: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Push to remote."""
        # Safety: refuse force-push to protected branches
        if force:
            target = branch
            if not target:
                ok, current = _run_git(
                    ["rev-parse", "--abbrev-ref", "HEAD"], cwd=self._cwd
                )
                target = current.strip() if ok else ""
            if target in PROTECTED_BRANCHES:
                return {
                    "success": False,
                    "error": (
                        f"Refusing force-push to protected branch '{target}'. "
                        "This could destroy shared history."
                    ),
                    "output": None,
                }

        args = ["push", remote]
        if branch:
            args.append(branch)
        if force:
            args.append("--force-with-lease")

        ok, out = _run_git(args, cwd=self._cwd, timeout=60)
        return {
            "success": ok,
            "output": out if ok else None,
            "error": out if not ok else None,
        }

    def _pull(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Pull from remote."""
        args = ["pull", remote]
        if branch:
            args.append(branch)

        ok, out = _run_git(args, cwd=self._cwd, timeout=60)
        return {
            "success": ok,
            "output": out if ok else None,
            "error": out if not ok else None,
        }

    def _stash(
        self,
        action: str = "list",
        message: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Stash operations."""
        if action == "push" or action == "save":
            args = ["stash", "push"]
            if message:
                args.extend(["-m", message])
        elif action == "pop":
            args = ["stash", "pop"]
        elif action == "list":
            args = ["stash", "list"]
        elif action == "drop":
            args = ["stash", "drop"]
        elif action == "show":
            args = ["stash", "show", "-p"]
        else:
            return {"success": False, "error": f"Unknown stash action: {action}", "output": None}

        ok, out = _run_git(args, cwd=self._cwd)
        return {
            "success": ok,
            "output": out if ok else None,
            "error": out if not ok else None,
        }

    def _merge(self, branch: str = "", **kwargs: Any) -> dict[str, Any]:
        """Merge a branch."""
        if not branch:
            return {
                "success": False,
                "error": "Branch name is required for merge",
                "output": None,
            }

        ok, out = _run_git(["merge", branch], cwd=self._cwd, timeout=60)
        return {
            "success": ok,
            "output": out if ok else None,
            "error": out if not ok else None,
        }

    def _create_pr(
        self,
        title: str = "",
        body: str = "",
        base: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a pull request using gh CLI."""
        if not title:
            return {"success": False, "error": "PR title is required", "output": None}

        try:
            args = ["gh", "pr", "create", "--title", title, "--body", body or ""]
            if base:
                args.extend(["--base", base])

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                cwd=self._cwd,
                timeout=30,
            )
            if result.returncode == 0:
                return {"success": True, "output": result.stdout.strip()}
            else:
                error = result.stderr.strip() or result.stdout.strip()
                # Check if gh is not installed
                if "not found" in error.lower() or "command not found" in error.lower():
                    return {
                        "success": False,
                        "error": (
                            "GitHub CLI (gh) is not installed. "
                            "Install it with: brew install gh"
                        ),
                        "output": None,
                    }
                return {"success": False, "error": error, "output": None}
        except FileNotFoundError:
            return {
                "success": False,
                "error": (
                    "GitHub CLI (gh) is not installed. Install it with: brew install gh"
                ),
                "output": None,
            }
