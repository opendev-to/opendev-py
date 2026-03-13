"""Main PluginsCommands class composing all mixin groups."""

import sys
from typing import Any

from rich.console import Console

from opendev.repl.commands.base import CommandHandler, CommandResult
from opendev.core.plugins import PluginManager
from opendev.repl.commands.plugins_commands.marketplace import MarketplaceCommandsMixin
from opendev.repl.commands.plugins_commands.install import InstallCommandsMixin
from opendev.repl.commands.plugins_commands.lifecycle import LifecycleCommandsMixin


class PluginsCommands(
    MarketplaceCommandsMixin, InstallCommandsMixin, LifecycleCommandsMixin, CommandHandler
):
    """Handler for /plugins command to manage plugins and marketplaces."""

    def __init__(
        self,
        console: Console,
        config_manager: Any,
        *,
        is_tui: bool = False,
    ):
        """Initialize plugins command handler.

        Args:
            console: Rich console for output
            config_manager: Configuration manager
            is_tui: Whether running inside the TUI (disables interactive prompts)
        """
        super().__init__(console)
        self.config_manager = config_manager
        self.plugin_manager = PluginManager(config_manager.working_dir)
        self._is_tui = is_tui

    def _can_prompt_interactively(self) -> bool:
        """Check if interactive prompts are available (not in TUI)."""
        return not self._is_tui and sys.stdin.isatty()

    def handle(self, args: str) -> CommandResult:
        """Handle /plugins command and subcommands.

        Args:
            args: Command arguments

        Returns:
            CommandResult with execution status
        """
        if not args:
            return self._show_menu()

        parts = args.split(maxsplit=1)
        subcmd = parts[0].lower()
        subcmd_args = parts[1] if len(parts) > 1 else ""

        if subcmd == "marketplace":
            return self._handle_marketplace(subcmd_args)
        elif subcmd == "install":
            return self._install_plugin(subcmd_args)
        elif subcmd == "uninstall" or subcmd == "remove":
            return self._uninstall_plugin(subcmd_args)
        elif subcmd == "update":
            return self._update_plugin(subcmd_args)
        elif subcmd == "list":
            return self._list_plugins()
        elif subcmd == "enable":
            return self._enable_plugin(subcmd_args)
        elif subcmd == "disable":
            return self._disable_plugin(subcmd_args)
        elif subcmd == "sync":
            return self._sync_plugin(subcmd_args)
        else:
            return self._show_menu()

    def _show_menu(self) -> CommandResult:
        """Show available plugins commands."""
        self.print_line("[cyan]/plugins list[/cyan]                    List installed plugins")
        self.print_continuation("[cyan]/plugins install <url>[/cyan]           Install plugin from URL")
        self.print_continuation("[cyan]/plugins uninstall <name>[/cyan]        Uninstall a plugin")
        self.print_continuation("[cyan]/plugins sync <name>[/cyan]             Update a plugin")
        self.print_continuation("[cyan]/plugins enable <name>[/cyan]           Enable a plugin")
        self.print_continuation("[cyan]/plugins disable <name>[/cyan]          Disable a plugin")
        self.console.print()

        return CommandResult(success=True)
