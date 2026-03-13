"""Centralized interrupt/cancellation token for a single agent run.

One token is created per user query execution. All components (LLM caller,
tool executor, HTTP client, etc.) share the same token so that a single
ESC press reliably cancels the entire operation regardless of which phase
is active.
"""

import ctypes
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Maximum number of async-exception injection retries
_MAX_FORCE_RETRIES = 3
_FORCE_RETRY_INTERVAL = 0.05  # 50ms between retries


class InterruptToken:
    """Thread-safe cancellation token shared across all components of a run.

    Usage:
        token = InterruptToken()
        # Pass to all execution components
        # UI calls token.force_interrupt() on ESC for immediate cancellation
        # Components poll token.is_requested() or call token.throw_if_requested()
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._thread_ident: Optional[int] = None
        self._http_cancel_callback: Optional[Callable] = None

    def set_thread_ident(self, ident: int) -> None:
        """Record the thread ID of the agent execution thread."""
        self._thread_ident = ident

    def set_http_cancel_callback(self, cb: Optional[Callable]) -> None:
        """Register a callback to cancel in-flight HTTP requests."""
        self._http_cancel_callback = cb

    def request(self) -> None:
        """Signal that the user wants to cancel the current operation."""
        self._event.set()

    def force_interrupt(self) -> None:
        """Brutally interrupt the agent thread immediately.

        Three-layer approach:
        1. Set the event flag (polling-based check)
        2. Cancel in-flight HTTP requests (socket-level)
        3. Inject InterruptedError into the agent thread (bytecode-level)
        """
        # Layer 1: Set the polling flag
        self._event.set()

        # Layer 2: Cancel HTTP connection
        if self._http_cancel_callback is not None:
            try:
                self._http_cancel_callback()
            except Exception:
                pass  # Best-effort; thread injection will handle it

        # Layer 3: Inject async exception into the agent thread
        if self._thread_ident is not None:
            self._inject_async_exception(self._thread_ident, attempt=1)

    def _inject_async_exception(self, ident: int, attempt: int) -> None:
        """Inject InterruptedError into the target thread via CPython API.

        Retries up to _MAX_FORCE_RETRIES times because C extensions and
        finally blocks can clear async exceptions before they take effect.
        """
        if not self._event.is_set():
            return  # Token was reset (e.g., new run started)

        try:
            ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(ident),
                ctypes.py_object(InterruptedError),
            )
            if ret == 0:
                logger.debug("Thread %d not found for async exception injection", ident)
                return
            if ret > 1:
                # Affected more than one thread — clear it (safety)
                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    ctypes.c_ulong(ident), None
                )
                logger.warning("Async exception injection hit multiple threads, cleared")
                return
        except Exception:
            logger.debug("PyThreadState_SetAsyncExc failed", exc_info=True)
            return

        # Schedule retry in case the exception was swallowed by a C extension
        if attempt < _MAX_FORCE_RETRIES:
            timer = threading.Timer(
                _FORCE_RETRY_INTERVAL,
                self._inject_async_exception,
                args=(ident, attempt + 1),
            )
            timer.daemon = True
            timer.start()

    def is_requested(self) -> bool:
        """Check whether cancellation has been requested.

        Returns:
            True if request() has been called.
        """
        return self._event.is_set()

    def throw_if_requested(self) -> None:
        """Raise InterruptedError if cancellation was requested.

        Raises:
            InterruptedError: When the token has been triggered.
        """
        if self._event.is_set():
            raise InterruptedError("Interrupted by user")

    def reset(self) -> None:
        """Clear the cancellation signal (use with care)."""
        self._event.clear()

    # Duck-typing compatibility with TaskMonitor interface so existing
    # code that calls ``monitor.should_interrupt()`` works unchanged.
    def should_interrupt(self) -> bool:
        """Alias for is_requested() — TaskMonitor compatibility."""
        return self.is_requested()

    def request_interrupt(self) -> None:
        """Alias for request() — TaskMonitor compatibility."""
        self.request()
