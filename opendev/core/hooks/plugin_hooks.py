"""In-process Python plugin hooks for tool execution.

Plugins are Python modules loaded from ~/.opendev/plugins/ and .opendev/plugins/
that can intercept tool calls and results. This provides ~100x faster hook
execution compared to shell-based hooks.

Plugin modules must define a register() function that returns a list of
PluginHook instances.

Example plugin (~/.opendev/plugins/my_plugin.py):

    from opendev.core.hooks.plugin_hooks import PluginHook

    class MyHook(PluginHook):
        def on_pre_tool_use(self, tool_name, args):
            if tool_name == "run_command" and "rm -rf" in args.get("command", ""):
                return {"blocked": True, "reason": "Dangerous command blocked"}
            return None

    def register():
        return [MyHook()]
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


class PluginHook(Protocol):
    """Protocol for in-process plugin hooks.

    Plugins implement one or both methods. Return None to pass through,
    or return a dict to modify behavior.
    """

    def on_pre_tool_use(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Called before a tool is executed.

        Args:
            tool_name: Name of the tool about to be executed.
            args: Tool arguments (can be modified in-place).

        Returns:
            None to continue execution, or a dict with:
            - {"blocked": True, "reason": "..."} to block execution
            - {"args": {...}} to replace arguments
        """
        ...

    def on_post_tool_use(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Called after a tool is executed.

        Args:
            tool_name: Name of the tool that was executed.
            args: Tool arguments that were used.
            result: Result dict from the tool.

        Returns:
            None to keep original result, or a modified result dict.
        """
        ...


class PluginHookManager:
    """Loads and manages in-process Python plugin hooks.

    Plugins are discovered from:
    1. ~/.opendev/plugins/*.py (user-level)
    2. .opendev/plugins/*.py (project-level)

    Each plugin module must have a register() function that returns
    a list of PluginHook instances.
    """

    def __init__(self, working_dir: Optional[str] = None) -> None:
        self._hooks: list[PluginHook] = []
        self._loaded_modules: set[str] = set()
        self._working_dir = Path(working_dir) if working_dir else Path.cwd()

    def discover_and_load(self) -> int:
        """Discover and load plugin hooks from standard directories.

        Returns:
            Number of hooks loaded.
        """
        plugin_dirs = [
            Path.home() / ".opendev" / "plugins",
            self._working_dir / ".opendev" / "plugins",
        ]

        count = 0
        for plugin_dir in plugin_dirs:
            if not plugin_dir.exists():
                continue
            for plugin_file in sorted(plugin_dir.glob("*.py")):
                if plugin_file.name.startswith("_"):
                    continue
                loaded = self._load_plugin(plugin_file)
                count += loaded

        if count > 0:
            logger.info("Loaded %d plugin hooks from %d directories", count, len(plugin_dirs))
        return count

    def _load_plugin(self, plugin_path: Path) -> int:
        """Load a single plugin module.

        Args:
            plugin_path: Path to the .py plugin file.

        Returns:
            Number of hooks loaded from this plugin.
        """
        module_id = str(plugin_path)
        if module_id in self._loaded_modules:
            return 0

        try:
            # Load module dynamically
            spec = importlib.util.spec_from_file_location(
                f"opendev_plugin_{plugin_path.stem}", plugin_path
            )
            if spec is None or spec.loader is None:
                logger.warning("Could not load plugin: %s", plugin_path)
                return 0

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Call register() to get hook instances
            register_fn = getattr(module, "register", None)
            if register_fn is None:
                logger.warning("Plugin %s has no register() function", plugin_path.name)
                return 0

            hooks = register_fn()
            if not isinstance(hooks, (list, tuple)):
                hooks = [hooks]

            count = 0
            for hook in hooks:
                if self._is_valid_hook(hook):
                    self._hooks.append(hook)
                    count += 1
                else:
                    logger.warning(
                        "Plugin %s returned invalid hook object: %s",
                        plugin_path.name,
                        type(hook).__name__,
                    )

            self._loaded_modules.add(module_id)
            if count > 0:
                logger.info("Loaded %d hooks from plugin: %s", count, plugin_path.name)
            return count

        except Exception as e:
            logger.error("Failed to load plugin %s: %s", plugin_path.name, e)
            return 0

    @staticmethod
    def _is_valid_hook(obj: Any) -> bool:
        """Check if an object implements the PluginHook protocol."""
        return hasattr(obj, "on_pre_tool_use") or hasattr(obj, "on_post_tool_use")

    def run_pre_hooks(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[dict[str, Any], bool, str]:
        """Run all pre-tool-use hooks.

        Args:
            tool_name: Tool name.
            args: Tool arguments.

        Returns:
            Tuple of (possibly modified args, should_continue, block_reason).
        """
        current_args = args
        for hook in self._hooks:
            if not hasattr(hook, "on_pre_tool_use"):
                continue
            try:
                result = hook.on_pre_tool_use(tool_name, current_args)
                if result is None:
                    continue
                if isinstance(result, dict):
                    if result.get("blocked"):
                        reason = result.get("reason", f"Blocked by {type(hook).__name__}")
                        return current_args, False, reason
                    if "args" in result:
                        current_args = result["args"]
            except Exception as e:
                logger.warning(
                    "Plugin hook %s.on_pre_tool_use failed: %s",
                    type(hook).__name__,
                    e,
                )
        return current_args, True, ""

    def run_post_hooks(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Run all post-tool-use hooks.

        Args:
            tool_name: Tool name.
            args: Tool arguments.
            result: Tool result dict.

        Returns:
            Possibly modified result dict.
        """
        current_result = result
        for hook in self._hooks:
            if not hasattr(hook, "on_post_tool_use"):
                continue
            try:
                modified = hook.on_post_tool_use(tool_name, args, current_result)
                if modified is not None and isinstance(modified, dict):
                    current_result = modified
            except Exception as e:
                logger.warning(
                    "Plugin hook %s.on_post_tool_use failed: %s",
                    type(hook).__name__,
                    e,
                )
        return current_result

    @property
    def hook_count(self) -> int:
        """Number of loaded hooks."""
        return len(self._hooks)

    def clear(self) -> None:
        """Remove all loaded hooks."""
        self._hooks.clear()
        self._loaded_modules.clear()
