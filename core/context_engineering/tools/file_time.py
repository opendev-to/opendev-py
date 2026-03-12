"""FileTime — stale-read detection for file edits.

Records the timestamp at which the agent last read each file. Before any
write/edit operation, assert_fresh() compares the file's mtime against
the recorded read time. If the file has been modified externally since
the agent's last read, the edit is rejected with an error instructing
the agent to re-read the file.

This prevents the agent from silently overwriting user edits made while
the agent was working — a significant data-loss risk.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Filesystem timestamp fuzziness tolerance (seconds).
# Most filesystems have 1-second mtime resolution; 50ms handles
# sub-second filesystems (ext4, APFS) while still catching real edits.
MTIME_TOLERANCE_SECS = 0.05


class FileTimeTracker:
    """Per-session tracker of file read timestamps for stale-read detection."""

    def __init__(self) -> None:
        # Maps absolute file path -> time.time() when agent last read it
        self._read_times: Dict[str, float] = {}
        self._lock = threading.Lock()

    def record_read(self, filepath: str) -> None:
        """Record that the agent just read this file.

        Args:
            filepath: Absolute path to the file that was read.
        """
        abs_path = os.path.abspath(filepath)
        now = time.time()
        with self._lock:
            self._read_times[abs_path] = now
        logger.debug("file_time: recorded read for %s at %.3f", abs_path, now)

    def assert_fresh(self, filepath: str) -> Optional[str]:
        """Check if a file has been modified since the agent last read it.

        Args:
            filepath: Absolute path to the file about to be edited.

        Returns:
            None if the file is fresh (safe to edit), or an error message
            string if the file is stale (must re-read first).
        """
        abs_path = os.path.abspath(filepath)

        with self._lock:
            read_time = self._read_times.get(abs_path)

        if read_time is None:
            # Agent never read this file — allow the edit but warn
            logger.debug("file_time: no read recorded for %s, allowing edit", abs_path)
            return None

        try:
            mtime = os.path.getmtime(abs_path)
        except OSError:
            # File doesn't exist (maybe deleted) — let the edit tool handle it
            return None

        if mtime > read_time + MTIME_TOLERANCE_SECS:
            logger.warning(
                "file_time: stale read detected for %s (mtime=%.3f > read_time=%.3f + %.3f)",
                abs_path,
                mtime,
                read_time,
                MTIME_TOLERANCE_SECS,
            )
            return (
                f"File `{filepath}` has been modified since you last read it "
                f"(file mtime is newer than your read time by "
                f"{mtime - read_time:.1f}s). "
                f"Re-read the file before editing to avoid overwriting changes."
            )

        return None

    def clear(self) -> None:
        """Clear all recorded read times (e.g., on session reset)."""
        with self._lock:
            self._read_times.clear()

    def invalidate(self, filepath: str) -> None:
        """Remove the read record for a file (e.g., after a successful edit).

        After editing a file, the agent's cached view is stale, so we remove
        the record to force a re-read before the next edit.

        Args:
            filepath: Absolute path to the file.
        """
        abs_path = os.path.abspath(filepath)
        with self._lock:
            self._read_times.pop(abs_path, None)
