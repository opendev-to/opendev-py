"""Tool execution middleware chain.

Provides a composable pipeline for tool execution. Each middleware can
inspect/modify tool arguments before execution and results after execution.

Usage:
    chain = MiddlewareChain()
    chain.add(ParamNormalizerMiddleware())
    chain.add(ResultSanitizerMiddleware())

    result = chain.execute(tool_name, args, handler_fn, ctx)
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Protocol

from opendev.core.context_engineering.tools.context import ToolExecutionContext

logger = logging.getLogger(__name__)


class ToolMiddleware(Protocol):
    """Protocol for tool execution middleware.

    Middlewares can modify arguments (before) and results (after).
    """

    def before(
        self,
        tool_name: str,
        args: dict[str, Any],
        ctx: ToolExecutionContext,
    ) -> tuple[dict[str, Any], bool]:
        """Pre-execution hook.

        Args:
            tool_name: Name of the tool being executed.
            args: Tool arguments (may be modified).
            ctx: Execution context.

        Returns:
            Tuple of (possibly modified args, should_continue).
            If should_continue is False, execution is short-circuited.
        """
        ...

    def after(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        ctx: ToolExecutionContext,
    ) -> dict[str, Any]:
        """Post-execution hook.

        Args:
            tool_name: Name of the tool that was executed.
            args: Tool arguments that were used.
            result: Result dict from the tool.
            ctx: Execution context.

        Returns:
            Possibly modified result dict.
        """
        ...


class MiddlewareChain:
    """Ordered chain of middlewares for tool execution.

    NOTE: Not currently instantiated — the tool registry calls normalizer
    and sanitizer directly. Reserved for future middleware chain expansion.
    """

    def __init__(self) -> None:
        self._middlewares: list[ToolMiddleware] = []

    def add(self, middleware: ToolMiddleware) -> None:
        """Add a middleware to the chain."""
        self._middlewares.append(middleware)

    def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        handler: Callable[..., dict[str, Any]],
        ctx: ToolExecutionContext,
    ) -> dict[str, Any]:
        """Execute through the middleware chain.

        1. Runs before() on each middleware in order
        2. Calls the handler
        3. Runs after() on each middleware in reverse order

        Args:
            tool_name: Tool name.
            args: Tool arguments.
            handler: The actual tool handler function.
            ctx: Execution context.

        Returns:
            Final result dict after all after() middlewares.
        """
        # Forward pass: before hooks
        current_args = args
        for mw in self._middlewares:
            try:
                current_args, should_continue = mw.before(tool_name, current_args, ctx)
                if not should_continue:
                    return {
                        "success": False,
                        "error": f"Blocked by middleware: {type(mw).__name__}",
                        "output": None,
                    }
            except Exception as e:
                logger.warning("Middleware %s.before() failed: %s", type(mw).__name__, e)
                # Continue with unchanged args

        # Execute handler
        result = handler(current_args, ctx)

        # Reverse pass: after hooks
        for mw in reversed(self._middlewares):
            try:
                result = mw.after(tool_name, current_args, result, ctx)
            except Exception as e:
                logger.warning("Middleware %s.after() failed: %s", type(mw).__name__, e)
                # Continue with unchanged result

        return result


# ===== Built-in Middleware Implementations =====


class ParamNormalizerMiddleware:
    """Middleware that normalizes tool parameters."""

    def __init__(self, working_dir: Optional[str] = None) -> None:
        self._working_dir = working_dir

    def before(
        self,
        tool_name: str,
        args: dict[str, Any],
        ctx: ToolExecutionContext,
    ) -> tuple[dict[str, Any], bool]:
        from opendev.core.context_engineering.tools.param_normalizer import normalize_params

        normalized = normalize_params(tool_name, args, self._working_dir)
        return normalized, True

    def after(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        ctx: ToolExecutionContext,
    ) -> dict[str, Any]:
        return result


class ResultSanitizerMiddleware:
    """Middleware that truncates large tool results."""

    def __init__(self, custom_limits: Optional[dict[str, int]] = None) -> None:
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer

        self._sanitizer = ToolResultSanitizer(custom_limits)

    def before(
        self,
        tool_name: str,
        args: dict[str, Any],
        ctx: ToolExecutionContext,
    ) -> tuple[dict[str, Any], bool]:
        return args, True

    def after(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        ctx: ToolExecutionContext,
    ) -> dict[str, Any]:
        return self._sanitizer.sanitize(tool_name, result)


class LoggingMiddleware:
    """Middleware that logs tool invocations and results."""

    def before(
        self,
        tool_name: str,
        args: dict[str, Any],
        ctx: ToolExecutionContext,
    ) -> tuple[dict[str, Any], bool]:
        logger.info("Tool call: %s(%s)", tool_name, list(args.keys()))
        return args, True

    def after(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        ctx: ToolExecutionContext,
    ) -> dict[str, Any]:
        success = result.get("success", False)
        logger.info("Tool result: %s -> %s", tool_name, "success" if success else "failed")
        return result
