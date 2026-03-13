"""File operation tools for reading, searching, and navigating codebases."""

import re
import subprocess
from pathlib import Path
from typing import Optional

from opendev.models.config import AppConfig

# Default directories/patterns to exclude from search
# Covers 20+ programming languages and ecosystems
DEFAULT_SEARCH_EXCLUDES = [
    # ===== Package/Dependency Directories =====
    "node_modules",  # JavaScript/TypeScript (npm, yarn, pnpm, bun)
    "bower_components",  # Bower (legacy JS)
    "jspm_packages",  # JSPM
    "vendor",  # Go, PHP (Composer), Ruby (Bundler)
    "Pods",  # Swift/Objective-C (CocoaPods)
    ".bundle",  # Ruby Bundler
    "packages",  # Dart/Flutter, .NET
    ".pub-cache",  # Dart pub
    ".pub",  # Dart pub
    "deps",  # Elixir Mix
    ".nuget",  # .NET NuGet
    ".m2",  # Java Maven, Clojure
    # ===== Virtual Environments =====
    ".venv",  # Python (standard)
    "venv",  # Python (common)
    "env",  # Python (common)
    ".env",  # Python/Node env dirs
    "ENV",  # Python
    ".virtualenvs",  # virtualenvwrapper
    ".conda",  # Conda environments
    # ===== Build Output Directories =====
    "build",  # Universal (C/C++, Python, Gradle, etc.)
    "dist",  # Universal (JS, Python, Haskell)
    "out",  # TypeScript, Android, general
    "target",  # Rust (Cargo), Java (Maven), Scala (sbt), Clojure
    "bin",  # .NET, Go, general compiled output
    "obj",  # .NET intermediate
    "lib",  # Compiled libraries
    "_build",  # Elixir, Erlang
    "ebin",  # Erlang compiled
    "dist-newstyle",  # Haskell Cabal
    ".build",  # Swift Package Manager
    "DerivedData",  # Xcode
    "CMakeFiles",  # CMake build artifacts
    ".cmake",  # CMake cache
    # ===== Framework-Specific Build =====
    ".next",  # Next.js
    ".nuxt",  # Nuxt.js
    ".angular",  # Angular CLI
    ".svelte-kit",  # SvelteKit
    ".vuepress",  # VuePress
    ".gatsby-cache",  # Gatsby
    ".parcel-cache",  # Parcel bundler
    ".turbo",  # Turborepo
    "dist_electron",  # Electron
    # ===== Cache Directories =====
    ".cache",  # Universal cache
    "__pycache__",  # Python bytecode
    ".pytest_cache",  # Pytest
    ".mypy_cache",  # Mypy type checker
    ".ruff_cache",  # Ruff linter
    ".hypothesis",  # Hypothesis testing
    ".tox",  # Tox testing
    ".nox",  # Nox testing
    ".eslintcache",  # ESLint
    ".stylelintcache",  # Stylelint
    ".gradle",  # Gradle
    ".dart_tool",  # Dart
    ".mix",  # Elixir
    ".cpcache",  # Clojure
    ".lsp",  # Clojure LSP
    # ===== IDE/Editor Directories =====
    ".idea",  # JetBrains IDEs
    ".vscode",  # VS Code
    ".vscode-test",  # VS Code extension testing
    ".vs",  # Visual Studio
    ".metadata",  # Eclipse
    ".settings",  # Eclipse
    "xcuserdata",  # Xcode user data
    ".netbeans",  # NetBeans
    # ===== Version Control =====
    ".git",  # Git
    ".svn",  # Subversion
    ".hg",  # Mercurial
    # ===== Coverage/Testing Output =====
    "coverage",  # Universal coverage
    "htmlcov",  # Python coverage HTML
    ".nyc_output",  # NYC (Istanbul) coverage
    # ===== Language-Specific Metadata =====
    ".eggs",  # Python eggs
    ".Rproj.user",  # R Studio
    ".julia",  # Julia packages
    "_opam",  # OCaml
    ".cabal-sandbox",  # Haskell Cabal sandbox
    ".stack-work",  # Haskell Stack
    "blib",  # Perl build
    # ===== Generated/Minified Files (glob patterns) =====
    "*.min.js",  # Minified JavaScript
    "*.min.css",  # Minified CSS
    "*.bundle.js",  # Bundled JavaScript
    "*.chunk.js",  # Webpack chunks
    "*.map",  # Source maps
    "*.pyc",  # Python compiled
    "*.pyo",  # Python optimized
    "*.class",  # Java compiled
    "*.o",  # C/C++ object files
    "*.so",  # Shared libraries
    "*.dylib",  # macOS dynamic libraries
    "*.dll",  # Windows DLLs
    "*.exe",  # Windows executables
    "*.beam",  # Erlang/Elixir compiled
    "*.hi",  # Haskell interface
    "*.dyn_hi",  # Haskell dynamic interface
    "*.dyn_o",  # Haskell dynamic object
    "*.egg-info",  # Python egg info
]


# Image extensions that can be base64-encoded for LLM
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
_PDF_EXTENSIONS = {".pdf"}


class FileOperations:
    """Tools for file operations."""

    def __init__(self, config: AppConfig, working_dir: Path):
        """Initialize file operations.

        Args:
            config: Application configuration
            working_dir: Working directory for operations
        """
        self.config = config
        self.working_dir = working_dir
        self._gitignore = None

    @property
    def gitignore(self):
        """Lazy-cached GitIgnoreParser instance."""
        if self._gitignore is None:
            try:
                from opendev.core.utils.gitignore import GitIgnoreParser

                self._gitignore = GitIgnoreParser(self.working_dir)
            except Exception:
                self._gitignore = False  # sentinel to avoid retrying
        return self._gitignore if self._gitignore is not False else None

    # Minimal fallback set when GitIgnoreParser is unavailable
    _FALLBACK_IGNORE_DIRS = {
        "__pycache__",
        ".git",
        "node_modules",
        ".pytest_cache",
        ".venv",
        "venv",
        ".mypy_cache",
        ".tox",
    }

    def _is_gitignored(self, path: str | Path) -> bool:
        """Check if a path is matched by .gitignore patterns."""
        gi = self.gitignore
        p = Path(path) if isinstance(path, str) else path
        if gi is None:
            # Fallback: at least filter well-known junk directories
            return p.name in self._FALLBACK_IGNORE_DIRS
        if not p.is_absolute():
            p = self.working_dir / p
        return gi.is_ignored(p)

    def _is_excluded_path(self, file_path: str) -> bool:
        """Check if path contains any excluded directory or matches excluded patterns."""
        path_obj = Path(file_path)
        path_parts = path_obj.parts

        for exclude in DEFAULT_SEARCH_EXCLUDES:
            if exclude.startswith("*"):
                # Glob pattern like *.min.js
                if path_obj.match(exclude):
                    return True
            elif exclude in path_parts:
                return True
        return False

    # Truncation constants
    DEFAULT_MAX_LINES = 2000
    MAX_LINE_LENGTH = 2000
    MAX_LIST_ENTRIES = 500

    @staticmethod
    def _is_binary_file(path: Path) -> bool:
        """Check if a file is binary by looking for null bytes and non-printable chars."""
        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
            # Check 1: Null bytes are definitive binary indicator
            if b"\x00" in chunk:
                return True
            # Check 2: High ratio of non-printable chars suggests binary
            if chunk:
                printable = set(range(0x20, 0x7F)) | {0x09, 0x0A, 0x0D}
                non_printable = sum(1 for b in chunk[:4096] if b not in printable)
                if non_printable / len(chunk[:4096]) > 0.30:
                    return True
            return False
        except OSError:
            return False

    def _read_image_file(self, path: Path) -> str:
        """Read an image file and return base64-encoded content."""
        import base64

        try:
            data = path.read_bytes()
            size_kb = len(data) / 1024
            if size_kb > 10_000:  # 10 MB limit
                return f"Error: Image file too large ({size_kb:.0f}KB). Max 10MB."

            b64 = base64.b64encode(data).decode("ascii")
            mime_type = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".bmp": "image/bmp",
                ".svg": "image/svg+xml",
            }.get(path.suffix.lower(), "image/png")

            return (
                f"[Image: {path.name} ({size_kb:.1f}KB, {mime_type})]\n"
                f"data:{mime_type};base64,{b64}"
            )
        except OSError as e:
            return f"Error reading image: {e}"

    def _read_pdf_file(self, path: Path, offset: int = 1, max_lines: int = 2000) -> str:
        """Read a PDF file and extract text content."""
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.split("\n")
                total = len(lines)
                start_idx = offset - 1
                end_idx = min(start_idx + max_lines, total)
                selected = lines[start_idx:end_idx]
                output_parts = []
                for i, line in enumerate(selected, start=offset):
                    text = line.rstrip()
                    if len(text) > self.MAX_LINE_LENGTH:
                        text = text[: self.MAX_LINE_LENGTH] + "... (line truncated)"
                    output_parts.append(f"  {i}\t{text}")
                result_text = "\n".join(output_parts)
                if end_idx < total:
                    result_text += f"\n... (truncated: showing lines {offset}-{end_idx} of {total})"
                return result_text
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: try PyMuPDF
        try:
            import fitz  # type: ignore[import-untyped]

            doc = fitz.open(str(path))
            text_parts = []
            for page_num in range(min(20, len(doc))):
                page = doc[page_num]
                text_parts.append(f"--- Page {page_num + 1} ---")
                text_parts.append(page.get_text())
            doc.close()
            return "\n".join(text_parts)
        except ImportError:
            pass

        return (
            "Error: Cannot read PDF. "
            "Install pdftotext (poppler) or PyMuPDF (pip install pymupdf)."
        )

    def read_file(
        self,
        file_path: str,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
        offset: Optional[int] = None,
        max_lines: Optional[int] = None,
    ) -> str:
        """Read a file's contents with line-numbered output and truncation.

        Args:
            file_path: Path to the file (relative or absolute).
            line_start: Optional starting line number (1-indexed). Alias for offset.
            line_end: Optional ending line number (1-indexed, inclusive).
            offset: Optional 1-indexed line number to start reading from.
            max_lines: Maximum number of lines to return (default 2000).

        Returns:
            File contents in ``cat -n`` format with line numbers.

        Raises:
            FileNotFoundError: If file doesn't exist.
            PermissionError: If file read is not permitted.
        """
        path = self._resolve_path(file_path)

        # Check permissions
        if not self.config.permissions.file_read.is_allowed(str(path)):
            raise PermissionError(f"Reading {path} is not permitted")

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        # Handle image files — return as base64 for multimodal LLMs
        suffix = path.suffix.lower()
        if suffix in _IMAGE_EXTENSIONS:
            return self._read_image_file(path)

        # Handle PDF files — extract text
        if suffix in _PDF_EXTENSIONS:
            effective_offset = offset or line_start or 1
            if effective_offset < 1:
                effective_offset = 1
            effective_max = max_lines if max_lines is not None else self.DEFAULT_MAX_LINES
            if line_end is not None:
                effective_max = line_end - effective_offset + 1
            return self._read_pdf_file(path, offset=effective_offset, max_lines=effective_max)

        # Detect binary files
        if self._is_binary_file(path):
            return f"Error: {path} appears to be a binary file. Cannot display binary content."

        # Determine effective start/limit
        effective_offset = offset or line_start or 1
        if effective_offset < 1:
            effective_offset = 1

        effective_max = max_lines if max_lines is not None else self.DEFAULT_MAX_LINES
        if line_end is not None:
            effective_max = line_end - effective_offset + 1

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        start_idx = effective_offset - 1
        end_idx = min(start_idx + effective_max, total_lines)
        selected = all_lines[start_idx:end_idx]

        # Format as cat -n style with line numbers
        output_parts: list[str] = []
        for i, line in enumerate(selected, start=effective_offset):
            text = line.rstrip("\n")
            # Truncate long lines
            if len(text) > self.MAX_LINE_LENGTH:
                text = text[: self.MAX_LINE_LENGTH] + "... (line truncated)"
            output_parts.append(f"  {i}\t{text}")

        result = "\n".join(output_parts)

        # Warn if file is gitignored
        if self._is_gitignored(path):
            name = path.name
            result = f"Note: {name} is in .gitignore (not tracked by git).\n\n" + result

        # Add truncation message if we didn't show everything
        if end_idx < total_lines:
            result += (
                f"\n... (truncated: showing lines {effective_offset}-{end_idx}"
                f" of {total_lines}. Use offset/max_lines to see more.)"
            )

        return result

    def glob_files(
        self,
        pattern: str,
        max_results: int = 100,
        base_path: Optional[Path] = None,
    ) -> list[str]:
        """Find files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "**/*.py", "src/**/*.ts")
            max_results: Maximum number of results to return
            base_path: Optional base directory to run the glob from

        Returns:
            List of matching file paths (relative to working_dir)
        """
        matches = []
        search_root = base_path or self.working_dir
        try:
            iterator = search_root.glob(pattern)
        except NotImplementedError:
            return [f"Error: Non-relative pattern '{pattern}' is not supported"]
        except Exception as e:
            return [f"Error: {str(e)}"]

        for path in iterator:
            if path.is_file():
                if self._is_gitignored(path):
                    continue
                matches.append(self._format_display_path(path))
                if len(matches) >= max_results:
                    break

        return matches

    def _format_display_path(self, path: Path) -> str:
        """Return a human-friendly representation of a path."""
        try:
            return str(path.relative_to(self.working_dir))
        except ValueError:
            return str(path)

    # Maximum character count for search output
    MAX_SEARCH_OUTPUT_CHARS = 30_000

    def grep_files(
        self,
        pattern: str,
        path: Optional[str] = None,
        context_lines: int = 0,
        max_results: int = 50,
        case_insensitive: bool = False,
        include_glob: Optional[str] = None,
        file_type: Optional[str] = None,
        fixed_string: bool = False,
        multiline: bool = False,
        output_mode: str = "content",
    ) -> list[dict[str, any]]:
        """Search for pattern in files.

        Args:
            pattern: Regex pattern to search for (or literal if fixed_string=True)
            path: Optional path/directory to search in (relative to working_dir)
            context_lines: Number of context lines to include
            max_results: Maximum number of matches
            case_insensitive: Case insensitive search
            include_glob: Glob pattern to filter files (e.g., "*.py")
            file_type: File type filter (e.g., "py", "js", "rust")
            fixed_string: Treat pattern as literal string, not regex
            multiline: Enable multiline matching
            output_mode: "content" (default), "files_with_matches", or "count"

        Returns:
            List of matches (format depends on output_mode)
        """
        matches = []

        try:
            # Use ripgrep if available for better performance
            use_json = output_mode == "content"

            cmd = ["rg"]
            if use_json:
                cmd.append("--json")

            if fixed_string:
                cmd.append("-F")
            if multiline:
                cmd.append("-U")
            if output_mode == "files_with_matches":
                cmd.append("--files-with-matches")
            elif output_mode == "count":
                cmd.append("--count")

            cmd.append(pattern)

            # Add default exclusions (ripgrep respects .gitignore, but this is a safety net)
            for exclude in DEFAULT_SEARCH_EXCLUDES:
                if exclude.startswith("*"):
                    cmd.extend(["--glob", f"!{exclude}"])
                else:
                    cmd.extend(["--glob", f"!{exclude}/**"])

            if include_glob:
                cmd.extend(["--glob", include_glob])
            if file_type:
                cmd.extend(["--type", file_type])
            if case_insensitive:
                cmd.append("-i")
            if context_lines > 0:
                cmd.extend(["-C", str(context_lines)])
            if max_results > 0:
                cmd.extend(["-m", str(max_results)])

            # Add the search path if specified
            if path and path not in (".", "./"):
                search_path = self.working_dir / path
                cmd.append(str(search_path))
            # If path is "." or "./" or not specified, ripgrep uses cwd (which we set below)

            result = subprocess.run(
                cmd,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                if output_mode == "files_with_matches":
                    for line in result.stdout.strip().split("\n"):
                        if not line:
                            continue
                        abs_path = str(self.working_dir / line)
                        matches.append({"file": abs_path})
                elif output_mode == "count":
                    for line in result.stdout.strip().split("\n"):
                        if not line or ":" not in line:
                            continue
                        # Format: file_path:count
                        sep = line.rfind(":")
                        file_path = line[:sep]
                        count = int(line[sep + 1 :])
                        abs_path = str(self.working_dir / file_path)
                        matches.append({"file": abs_path, "count": count})
                else:
                    # content mode — JSON parsing
                    for line in result.stdout.strip().split("\n"):
                        if not line:
                            continue
                        try:
                            import json

                            data = json.loads(line)
                            if data["type"] == "match":
                                match_data = data["data"]
                                file_path = match_data["path"]["text"]
                                abs_path = str(self.working_dir / file_path)
                                matches.append(
                                    {
                                        "file": abs_path,
                                        "line": match_data["line_number"],
                                        "content": match_data["lines"]["text"].strip(),
                                    }
                                )
                                if len(matches) >= max_results:
                                    break
                        except Exception:
                            continue

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Fallback to Python-based search if rg is not available
            matches = self._python_grep(
                pattern,
                path,
                max_results,
                case_insensitive,
                include_glob=include_glob,
                file_type=file_type,
                fixed_string=fixed_string,
                multiline=multiline,
                output_mode=output_mode,
            )

        return matches

    # File type to extension mapping for Python grep fallback
    _FILE_TYPE_EXTENSIONS: dict[str, set[str]] = {
        "py": {".py", ".pyi"},
        "js": {".js", ".jsx", ".mjs"},
        "ts": {".ts", ".tsx", ".mts"},
        "rust": {".rs"},
        "go": {".go"},
        "java": {".java"},
        "c": {".c", ".h"},
        "cpp": {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"},
        "ruby": {".rb"},
        "php": {".php"},
        "swift": {".swift"},
        "kotlin": {".kt", ".kts"},
        "scala": {".scala"},
        "html": {".html", ".htm"},
        "css": {".css"},
        "json": {".json"},
        "yaml": {".yaml", ".yml"},
        "toml": {".toml"},
        "md": {".md", ".markdown"},
        "sh": {".sh", ".bash", ".zsh"},
    }

    def _python_grep(
        self,
        pattern: str,
        search_path: Optional[str],
        max_results: int,
        case_insensitive: bool,
        include_glob: Optional[str] = None,
        file_type: Optional[str] = None,
        fixed_string: bool = False,
        multiline: bool = False,
        output_mode: str = "content",
    ) -> list[dict[str, any]]:
        """Fallback grep implementation using Python."""
        import fnmatch as _fnmatch

        matches = []
        flags = re.IGNORECASE if case_insensitive else 0
        if multiline:
            flags |= re.DOTALL | re.MULTILINE

        raw_pattern = re.escape(pattern) if fixed_string else pattern
        regex = re.compile(raw_pattern, flags)

        # Resolve file type extensions
        type_exts = self._FILE_TYPE_EXTENSIONS.get(file_type) if file_type else None

        # Determine search root and glob pattern
        if search_path in (None, ".", "./"):
            search_root = self.working_dir
            glob_pattern = "**/*"
        else:
            search_path_obj = Path(search_path)
            if search_path_obj.is_absolute():
                if search_path_obj.is_dir():
                    search_root = search_path_obj
                    glob_pattern = "**/*"
                elif search_path_obj.is_file():
                    search_root = search_path_obj.parent
                    glob_pattern = search_path_obj.name
                else:
                    return matches
            else:
                resolved = self.working_dir / search_path
                if resolved.is_dir():
                    search_root = resolved
                    glob_pattern = "**/*"
                elif resolved.is_file():
                    search_root = resolved.parent
                    glob_pattern = resolved.name
                else:
                    search_root = self.working_dir
                    glob_pattern = search_path

        # Track per-file counts and seen files for non-content modes
        file_counts: dict[str, int] = {}
        seen_files: list[str] = []

        for path in search_root.glob(glob_pattern):
            if not path.is_file():
                continue

            # Skip excluded and gitignored paths
            if self._is_excluded_path(str(path)):
                continue
            if self._is_gitignored(path):
                continue

            # Apply include_glob filter
            if include_glob and not _fnmatch.fnmatch(path.name, include_glob):
                continue

            # Apply file_type filter
            if type_exts and path.suffix not in type_exts:
                continue

            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    abs_path = str(path)

                    if multiline:
                        content = f.read()
                        found = list(regex.finditer(content))
                        if not found:
                            continue

                        if output_mode == "files_with_matches":
                            seen_files.append(abs_path)
                            if len(seen_files) >= max_results:
                                break
                        elif output_mode == "count":
                            file_counts[abs_path] = len(found)
                        else:
                            # Compute line numbers from match positions
                            for m in found:
                                line_num = content[: m.start()].count("\n") + 1
                                match_text = m.group(0)
                                # Truncate long multiline matches
                                if len(match_text) > 200:
                                    match_text = match_text[:200] + "..."
                                matches.append(
                                    {
                                        "file": abs_path,
                                        "line": line_num,
                                        "content": match_text.strip(),
                                    }
                                )
                                if len(matches) >= max_results:
                                    return matches
                    else:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                if output_mode == "files_with_matches":
                                    seen_files.append(abs_path)
                                    if len(seen_files) >= max_results:
                                        return [{"file": fp} for fp in seen_files]
                                    break  # One match is enough for this file
                                elif output_mode == "count":
                                    file_counts[abs_path] = file_counts.get(abs_path, 0) + 1
                                else:
                                    matches.append(
                                        {
                                            "file": abs_path,
                                            "line": line_num,
                                            "content": line.strip(),
                                        }
                                    )
                                    if len(matches) >= max_results:
                                        return matches
            except Exception:
                continue

        # Return based on output_mode
        if output_mode == "files_with_matches":
            return [{"file": fp} for fp in seen_files]
        elif output_mode == "count":
            return [{"file": fp, "count": c} for fp, c in file_counts.items()]

        return matches

    def list_directory(self, path: str = ".", max_depth: int = 2) -> str:
        """List directory contents as a tree.

        Args:
            path: Directory path (relative or absolute)
            max_depth: Maximum depth to traverse

        Returns:
            Directory tree as string
        """
        dir_path = self._resolve_path(path)

        if not dir_path.exists():
            return f"Directory not found: {dir_path}"

        if not dir_path.is_dir():
            return f"Not a directory: {dir_path}"

        return self._build_tree(dir_path, max_depth=max_depth)

    def _build_tree(
        self, path: Path, prefix: str = "", max_depth: int = 2, current_depth: int = 0
    ) -> str:
        """Build a tree representation of directory structure."""
        if current_depth >= max_depth:
            return ""

        lines = []
        try:
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            # Filter out gitignored and common ignore patterns
            items = [item for item in items if not self._is_gitignored(item)]

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                current_prefix = "└── " if is_last else "├── "
                next_prefix = "    " if is_last else "│   "

                lines.append(f"{prefix}{current_prefix}{item.name}")

                if item.is_dir():
                    subtree = self._build_tree(
                        item,
                        prefix + next_prefix,
                        max_depth,
                        current_depth + 1,
                    )
                    if subtree:
                        lines.append(subtree)

        except PermissionError:
            lines.append(f"{prefix}[Permission Denied]")

        return "\n".join(lines)

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

    def ast_grep(
        self,
        pattern: str,
        path: Optional[str] = None,
        lang: Optional[str] = None,
        max_results: int = 50,
    ) -> list[dict[str, any]]:
        """Search for AST patterns using ast-grep.

        ast-grep matches code structure, not text. Use $VAR wildcards to match
        any AST node (similar to regex .* but for syntax trees).

        Args:
            pattern: AST pattern with $VAR wildcards (e.g., '$A && $A()')
            path: Directory to search (relative to working_dir)
            lang: Language hint (auto-detected from file extension if not specified)
            max_results: Maximum matches to return

        Returns:
            List of matches with file, line, and matched code

        Raises:
            FileNotFoundError: If ast-grep (sg) is not installed
        """
        import json

        cmd = ["sg", "--json", "-p", pattern]

        if lang:
            cmd.extend(["-l", lang])

        search_path = str(self.working_dir / path) if path else str(self.working_dir)
        cmd.append(search_path)

        result = subprocess.run(
            cmd,
            cwd=self.working_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        matches = []
        if result.returncode == 0 and result.stdout.strip():
            try:
                # ast-grep outputs a JSON array, not newline-delimited objects
                data = json.loads(result.stdout)
                if isinstance(data, list):
                    for item in data:
                        file_path = item.get("file", "")

                        # Skip excluded and gitignored paths
                        if self._is_excluded_path(file_path):
                            continue
                        if self._is_gitignored(file_path):
                            continue

                        # Make path relative to working_dir for cleaner output
                        try:
                            rel_path = str(Path(file_path).relative_to(self.working_dir))
                        except ValueError:
                            rel_path = file_path

                        matches.append(
                            {
                                "file": rel_path,
                                "line": item.get("range", {}).get("start", {}).get("line", 0),
                                "content": item.get("text", "").strip(),
                            }
                        )

                        if len(matches) >= max_results:
                            break
            except json.JSONDecodeError:
                pass  # Invalid JSON, return empty matches

        return matches
