"""GitIgnore parser utility for filtering files based on .gitignore patterns."""

import os
from pathlib import Path
from typing import Optional

import pathspec
from pathspec import PathSpec


class GitIgnoreParser:
    """Parser for .gitignore files that supports nested gitignore files.

    This class loads and parses .gitignore files from a root directory
    and all its subdirectories, providing methods to check if paths
    should be ignored based on gitignore patterns.
    """

    # Always ignore these directories regardless of .gitignore
    ALWAYS_IGNORE_DIRS = {
        # Version Control
        ".git",
        ".hg",
        ".svn",
        ".bzr",
        "_darcs",
        ".fossil",
        # OS Generated
        ".DS_Store",
        ".Spotlight-V100",
        ".Trashes",
        "Thumbs.db",
        "desktop.ini",
        "$RECYCLE.BIN",
        # Python caches
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".pytype",
        ".pyre",
        ".hypothesis",
        ".tox",
        ".nox",
        "cython_debug",
        ".eggs",
        # Node/JS caches
        "node_modules",
        ".npm",
        ".yarn",
        ".pnpm-store",
        ".next",
        ".nuxt",
        ".output",
        ".svelte-kit",
        ".angular",
        ".parcel-cache",
        ".turbo",
        # IDE/Editor
        ".idea",
        ".vscode",
        ".vs",
        ".settings",
        # Java/Kotlin
        ".gradle",
        # Elixir
        "_build",
        "deps",
        ".elixir_ls",
        # iOS
        "Pods",
        "DerivedData",
        "xcuserdata",
        # Ruby
        ".bundle",
        # Virtual Environments
        ".venv",
        "venv",
        # Misc caches
        ".cache",
        ".sass-cache",
        ".eslintcache",
        ".stylelintcache",
        ".tmp",
        ".temp",
        "tmp",
        "temp",
    }

    def __init__(self, root_dir: Path):
        """Initialize the GitIgnore parser.

        Args:
            root_dir: Root directory to start parsing from
        """
        self.root_dir = root_dir.resolve()
        self._specs: list[tuple[Path, PathSpec]] = []
        self._load_gitignore_files()

    def _load_gitignore_files(self) -> None:
        """Find and parse all .gitignore files in the directory tree."""
        root_gitignore = self.root_dir / ".gitignore"
        if root_gitignore.exists():
            spec = self._parse_gitignore(root_gitignore)
            if spec:
                self._specs.append((self.root_dir, spec))

        try:
            for root, dirs, files in os.walk(self.root_dir):
                dirs[:] = [d for d in dirs if d not in self.ALWAYS_IGNORE_DIRS]

                root_path = Path(root)

                if root_path == self.root_dir:
                    continue

                gitignore_path = root_path / ".gitignore"
                if gitignore_path.exists():
                    spec = self._parse_gitignore(gitignore_path)
                    if spec:
                        self._specs.append((root_path, spec))
        except (PermissionError, OSError):
            pass

    def _parse_gitignore(self, gitignore_path: Path) -> Optional[PathSpec]:
        """Parse a single .gitignore file."""
        try:
            with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            patterns = []
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                patterns.append(line)

            if patterns:
                return pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, patterns)
        except (IOError, OSError):
            pass

        return None

    def is_ignored(self, path: Path) -> bool:
        """Check if a path should be ignored based on gitignore patterns."""
        if not path.is_absolute():
            path = self.root_dir / path

        path = path.resolve()

        try:
            rel_path = path.relative_to(self.root_dir)
        except ValueError:
            return False

        for part in rel_path.parts:
            if part in self.ALWAYS_IGNORE_DIRS:
                return True

        for spec_dir, spec in self._specs:
            try:
                path.relative_to(spec_dir)
            except ValueError:
                continue

            try:
                match_path = path.relative_to(spec_dir)
            except ValueError:
                continue

            match_str = str(match_path).replace(os.sep, "/")

            if path.is_dir() and not match_str.endswith("/"):
                match_str += "/"

            if spec.match_file(match_str):
                return True

        return False

    def should_skip_dir(self, dir_path: Path) -> bool:
        """Check if a directory should be skipped during traversal."""
        dir_name = dir_path.name

        if dir_name in self.ALWAYS_IGNORE_DIRS:
            return True

        return self.is_ignored(dir_path)

    def filter_paths(self, paths: list[Path]) -> list[Path]:
        """Filter a list of paths, removing ignored ones."""
        return [p for p in paths if not self.is_ignored(p)]
