"""File system watcher for detecting external changes.

Uses the watchdog library to monitor the project directory for file
modifications made outside of OpenDev (e.g., by the user's editor).
Publishes events via the event bus and invalidates stale reads.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class FileChangeEvent:
    """Represents an external file change."""

    def __init__(self, path: str, event_type: str, is_directory: bool = False):
        self.path = path
        self.event_type = event_type  # "created", "modified", "deleted", "moved"
        self.is_directory = is_directory
        self.timestamp = time.time()


class FileWatcher:
    """Watches project directory for external file changes.

    Integrates with the event bus to notify the system of changes
    and can invalidate file read timestamps for stale-read detection.
    """

    def __init__(
        self,
        project_dir: Path,
        on_change: Optional[Callable[[FileChangeEvent], None]] = None,
        ignore_patterns: Optional[list[str]] = None,
    ):
        self._project_dir = project_dir
        self._on_change = on_change
        self._observer = None
        self._running = False
        self._ignore_patterns = ignore_patterns or [
            "*.pyc",
            "__pycache__",
            ".git",
            "node_modules",
            ".venv",
            "*.swp",
            "*.swo",
            "*~",
            ".DS_Store",
        ]
        # Track files we've recently written (to suppress self-triggered events)
        self._suppress_until: dict[str, float] = {}
        self._suppress_window = 2.0  # Ignore events within 2s of our own writes

    def suppress_path(self, path: str) -> None:
        """Temporarily suppress change events for a path (we just wrote it)."""
        self._suppress_until[str(Path(path).resolve())] = time.time() + self._suppress_window

    def _should_ignore(self, path: str) -> bool:
        """Check if a path should be ignored."""
        p = Path(path)
        # Check suppression
        resolved = str(p.resolve())
        if resolved in self._suppress_until:
            if time.time() < self._suppress_until[resolved]:
                return True
            del self._suppress_until[resolved]
        # Check ignore patterns
        import fnmatch

        for pattern in self._ignore_patterns:
            if fnmatch.fnmatch(p.name, pattern):
                return True
            if any(fnmatch.fnmatch(part, pattern) for part in p.parts):
                return True
        return False

    def start(self) -> bool:
        """Start watching for file changes.

        Returns:
            True if watcher started successfully, False if watchdog not available.
        """
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileSystemEvent
        except ImportError:
            logger.debug("watchdog not installed, file watching disabled")
            return False

        watcher = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event: FileSystemEvent) -> None:
                if watcher._should_ignore(event.src_path):
                    return

                event_type_map = {
                    "created": "created",
                    "modified": "modified",
                    "deleted": "deleted",
                    "moved": "moved",
                }
                evt_type = event_type_map.get(event.event_type)
                if not evt_type:
                    return

                change = FileChangeEvent(
                    path=event.src_path,
                    event_type=evt_type,
                    is_directory=event.is_directory,
                )

                if watcher._on_change:
                    try:
                        watcher._on_change(change)
                    except Exception:
                        logger.debug("File change callback failed", exc_info=True)

                # Publish to event bus
                try:
                    from opendev.core.events import get_bus, EventType

                    get_bus().emit(
                        EventType.FILE_EXTERNAL_CHANGE,
                        source="file_watcher",
                        path=event.src_path,
                        event_type=evt_type,
                    )
                except Exception:
                    pass

        self._observer = Observer()
        self._observer.schedule(Handler(), str(self._project_dir), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        self._running = True
        logger.debug("File watcher started for %s", self._project_dir)
        return True

    def stop(self) -> None:
        """Stop watching for file changes."""
        if self._observer and self._running:
            self._observer.stop()
            try:
                self._observer.join(timeout=5)
            except Exception:
                pass
            self._running = False
            logger.debug("File watcher stopped")

    @property
    def is_running(self) -> bool:
        return self._running
