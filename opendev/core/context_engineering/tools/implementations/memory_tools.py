"""Memory tools — search and write agent memory files."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryMatch:
    """A single search result from memory files."""
    file_path: str
    line_start: int
    line_end: int
    snippet: str
    score: float


class MemoryTools:
    """Search and write to agent memory files.

    Memory files live in:
    - Project-level: .opendev/memory/*.md (and OPENDEV.md)
    - User-level: ~/.opendev/memory/*.md
    """

    def __init__(self, working_dir: Optional[str] = None) -> None:
        self._working_dir = Path(working_dir) if working_dir else Path.cwd()

    def _get_memory_dirs(self) -> list[Path]:
        """Get all memory directories to search."""
        dirs = []
        # Project-level
        project_memory = self._working_dir / ".opendev" / "memory"
        if project_memory.exists():
            dirs.append(project_memory)
        # User-level
        user_memory = Path.home() / ".opendev" / "memory"
        if user_memory.exists():
            dirs.append(user_memory)
        return dirs

    def _get_memory_files(self) -> list[Path]:
        """Get all memory files to search."""
        files = []
        # Check for OPENDEV.md at project root
        opendev_md = self._working_dir / "OPENDEV.md"
        if opendev_md.exists():
            files.append(opendev_md)
        # Check for .opendev/MEMORY.md
        project_memory_md = self._working_dir / ".opendev" / "MEMORY.md"
        if project_memory_md.exists():
            files.append(project_memory_md)
        # Glob all .md files in memory dirs
        for d in self._get_memory_dirs():
            files.extend(sorted(d.glob("*.md")))
        return files

    def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> dict:
        """Search across all memory files using keyword matching.

        Args:
            query: Search query string
            max_results: Maximum number of results to return

        Returns:
            Result dict with matches
        """
        if not query or not query.strip():
            return {"success": False, "error": "Query cannot be empty", "output": None}

        files = self._get_memory_files()
        if not files:
            return {
                "success": True,
                "output": "No memory files found. Memory files are stored in .opendev/memory/ (project) or ~/.opendev/memory/ (user).",
                "matches": [],
            }

        # Tokenize query into keywords
        keywords = [w.lower() for w in re.split(r'\W+', query) if len(w) >= 2]
        if not keywords:
            return {"success": False, "error": "Query must contain searchable keywords", "output": None}

        matches: list[MemoryMatch] = []

        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            lines = content.split("\n")
            # Score each chunk (groups of ~10 lines with overlap)
            chunk_size = 10
            overlap = 3
            i = 0
            while i < len(lines):
                chunk_end = min(i + chunk_size, len(lines))
                chunk_lines = lines[i:chunk_end]
                chunk_text = "\n".join(chunk_lines)
                chunk_lower = chunk_text.lower()

                # Score: count keyword hits
                score = sum(
                    chunk_lower.count(kw) for kw in keywords
                )
                if score > 0:
                    # Make path relative for display
                    try:
                        display_path = str(file_path.relative_to(self._working_dir))
                    except ValueError:
                        display_path = str(file_path)

                    matches.append(MemoryMatch(
                        file_path=display_path,
                        line_start=i + 1,
                        line_end=chunk_end,
                        snippet=chunk_text[:500],
                        score=score,
                    ))
                i += chunk_size - overlap

        # Sort by score descending, then diversify across files
        matches.sort(key=lambda m: m.score, reverse=True)

        # Diversity: max 2 chunks per file, then fill remaining slots
        seen_files: dict[str, int] = {}
        diverse_matches: list[MemoryMatch] = []
        remaining: list[MemoryMatch] = []
        for match in matches:
            count = seen_files.get(match.file_path, 0)
            if count < 2:
                diverse_matches.append(match)
                seen_files[match.file_path] = count + 1
            else:
                remaining.append(match)
        top_matches = (diverse_matches + remaining)[:max_results]

        if not top_matches:
            return {
                "success": True,
                "output": f"No matches found for '{query}' in {len(files)} memory files.",
                "matches": [],
            }

        # Format output
        output_parts = [f"Found {len(top_matches)} matches across {len(files)} memory files:\n"]
        for i, m in enumerate(top_matches, 1):
            output_parts.append(
                f"--- Match {i} (score: {m.score:.1f}) ---\n"
                f"File: {m.file_path} (lines {m.line_start}-{m.line_end})\n"
                f"{m.snippet}\n"
            )

        return {
            "success": True,
            "output": "\n".join(output_parts),
            "matches": [
                {
                    "file_path": m.file_path,
                    "line_start": m.line_start,
                    "line_end": m.line_end,
                    "snippet": m.snippet,
                    "score": m.score,
                }
                for m in top_matches
            ],
        }

    def write(
        self,
        topic: str,
        content: str,
        file: Optional[str] = None,
        scope: str = "project",
    ) -> dict:
        """Write or update a memory entry.

        Args:
            topic: Topic name (used to generate filename if file not specified)
            content: Content to write
            file: Optional specific filename (without path)
            scope: "project" or "user" level

        Returns:
            Result dict
        """
        if not topic or not topic.strip():
            return {"success": False, "error": "Topic cannot be empty", "output": None}
        if not content or not content.strip():
            return {"success": False, "error": "Content cannot be empty", "output": None}

        # Determine target directory
        if scope == "user":
            target_dir = Path.home() / ".opendev" / "memory"
        else:
            target_dir = self._working_dir / ".opendev" / "memory"

        target_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename from topic if not provided
        if file:
            filename = file if file.endswith(".md") else f"{file}.md"
        else:
            # Slugify topic
            slug = re.sub(r'[^\w\s-]', '', topic.lower())
            slug = re.sub(r'[\s_]+', '-', slug).strip('-')
            filename = f"{slug}.md"

        file_path = target_dir / filename

        # Check for existing content to avoid duplicates
        if file_path.exists():
            existing = file_path.read_text(encoding="utf-8")
            # Check if content already exists (simple substring check)
            if content.strip() in existing:
                return {
                    "success": True,
                    "output": f"Memory already contains this content: {file_path}",
                }
            # Append to existing file
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n## {topic}\n\n{content.strip()}\n")
            action = "Updated"
        else:
            # Create new file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# {topic}\n\n{content.strip()}\n")
            action = "Created"

        try:
            display_path = str(file_path.relative_to(self._working_dir))
        except ValueError:
            display_path = str(file_path)

        return {
            "success": True,
            "output": f"{action} memory file: {display_path}",
            "file_path": display_path,
        }
