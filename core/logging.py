"""Structured logging with service tags and timing support."""

import json
import logging
import time
from contextlib import contextmanager
from typing import Any


class ServiceLogger:
    """Logger with service context and structured output."""

    def __init__(self, service: str, logger: logging.Logger | None = None):
        self._service = service
        self._logger = logger or logging.getLogger(f"opendev.{service}")

    def info(self, event: str, **data: Any) -> None:
        self._log(logging.INFO, event, data)

    def warning(self, event: str, **data: Any) -> None:
        self._log(logging.WARNING, event, data)

    def error(self, event: str, **data: Any) -> None:
        self._log(logging.ERROR, event, data)

    def debug(self, event: str, **data: Any) -> None:
        self._log(logging.DEBUG, event, data)

    @contextmanager
    def timer(self, event: str, **data: Any):
        """Context manager that logs duration of an operation."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._log(logging.INFO, event, {**data, "duration_ms": round(elapsed_ms, 1)})

    def _log(self, level: int, event: str, data: dict[str, Any]) -> None:
        extra = {"service": self._service, "event": event}
        if data:
            extra["data"] = data
        self._logger.log(
            level,
            "[%s] %s %s",
            self._service,
            event,
            json.dumps(data) if data else "",
        )


def create_logger(service: str) -> ServiceLogger:
    """Create a service-tagged logger."""
    return ServiceLogger(service)
