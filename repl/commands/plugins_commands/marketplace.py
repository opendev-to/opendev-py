"""Marketplace subcommands for plugins."""

from rich.prompt import Confirm
from rich.table import Table

from opendev.repl.commands.base import CommandResult
from opendev.core.plugins import (
    PluginManagerError,
    MarketplaceNotFoundError,
)


class MarketplaceCommandsMixin:
    """Mixin for marketplace-related commands."""

    def _handle_marketplace(self, args: str) -> CommandResult:
        """Handle marketplace subcommands.

        Args:
            args: Marketplace subcommand arguments

        Returns:
            CommandResult with execution status
        """
        if not args:
            return self._list_marketplaces()

        parts = args.split(maxsplit=1)
        subcmd = parts[0].lower()
        subcmd_args = parts[1] if len(parts) > 1 else ""

        if subcmd == "add":
            return self._add_marketplace(subcmd_args)
        elif subcmd == "list":
            return self._list_marketplaces()
        elif subcmd == "sync":
            return self._sync_marketplace(subcmd_args)
        elif subcmd == "remove":
            return self._remove_marketplace(subcmd_args)
        elif subcmd == "plugins":
            return self._list_marketplace_plugins(subcmd_args)
        else:
            self.print_error(f"Unknown marketplace command: {subcmd}")
            return CommandResult(success=False, message=f"Unknown command: {subcmd}")

    def _add_marketplace(self, url: str) -> CommandResult:
        """Add a marketplace by URL.

        Args:
            url: Git URL of the marketplace

        Returns:
            CommandResult with execution status
        """
        if not url:
            self.print_error("URL required: /plugins marketplace add <url>")
            return CommandResult(success=False, message="URL required")

        # Optionally get name
        name = None
        if " " in url:
            parts = url.split(maxsplit=1)
            url = parts[0]
            if parts[1].startswith("--name="):
                name = parts[1].replace("--name=", "")

        self.print_command_header("Adding marketplace", url)

        try:
            info = self.plugin_manager.add_marketplace(url, name=name)
            self.print_success(f"Added marketplace: [cyan]{info.name}[/cyan]")
            self.print_continuation(f"URL: {info.url}")
            self.print_continuation(f"Branch: {info.branch}")
            self.console.print()

            # Show available plugins
            try:
                plugins = self.plugin_manager.list_marketplace_plugins(info.name)
                if plugins:
                    self.print_info(f"Found {len(plugins)} plugin(s):")
                    for plugin in plugins[:5]:
                        self.print_continuation(f"  - {plugin.name}: {plugin.description[:50]}...")
                    if len(plugins) > 5:
                        self.print_continuation(f"  ... and {len(plugins) - 5} more")
                    self.console.print()
            except Exception:
                pass

            return CommandResult(success=True, message=f"Added marketplace: {info.name}", data=info)

        except PluginManagerError as e:
            self.print_error(str(e))
            return CommandResult(success=False, message=str(e))

    def _list_marketplaces(self) -> CommandResult:
        """List known marketplaces.

        Returns:
            CommandResult with execution status
        """
        marketplaces = self.plugin_manager.list_marketplaces()

        if not marketplaces:
            self.print_info("No marketplaces registered.")
            self.print_continuation("Add one with: /plugins marketplace add <url>")
            self.console.print()
            return CommandResult(success=True)

        table = Table(show_header=True, header_style="bold")
        table.add_column("Name", style="cyan")
        table.add_column("URL")
        table.add_column("Branch", style="dim")
        table.add_column("Last Synced", style="dim")

        for mp in marketplaces:
            last_updated = (
                mp.last_updated.strftime("%Y-%m-%d %H:%M") if mp.last_updated else "Never"
            )
            table.add_row(mp.name, mp.url, mp.branch, last_updated)

        self.console.print(table)
        self.console.print()

        return CommandResult(success=True, data=marketplaces)

    def _sync_marketplace(self, name: str) -> CommandResult:
        """Sync marketplace(s).

        Args:
            name: Marketplace name or empty for all

        Returns:
            CommandResult with execution status
        """
        if not name:
            # Sync all
            self.print_command_header("Syncing all marketplaces")
            results = self.plugin_manager.sync_all_marketplaces()

            success_count = sum(1 for v in results.values() if v is None)
            fail_count = len(results) - success_count

            for mp_name, error in results.items():
                if error:
                    self.print_error(f"{mp_name}: {error}")
                else:
                    self.print_success(f"{mp_name}: synced")

            self.console.print()
            self.print_info(f"Synced {success_count}/{len(results)} marketplace(s)")
            self.console.print()

            return CommandResult(
                success=fail_count == 0,
                message=f"Synced {success_count}/{len(results)} marketplaces",
            )
        else:
            # Sync specific marketplace
            self.print_command_header("Syncing marketplace", name)

            try:
                self.plugin_manager.sync_marketplace(name)
                self.print_success(f"Synced: {name}")
                self.console.print()
                return CommandResult(success=True, message=f"Synced: {name}")
            except (MarketplaceNotFoundError, PluginManagerError) as e:
                self.print_error(str(e))
                return CommandResult(success=False, message=str(e))

    def _remove_marketplace(self, args: str) -> CommandResult:
        """Remove a marketplace.

        Args:
            args: Marketplace name and optional flags (--force/-f)

        Returns:
            CommandResult with execution status
        """
        # Parse --force flag
        parts = args.split()
        name = ""
        force = False
        for part in parts:
            if part in ("--force", "-f"):
                force = True
            elif not name:
                name = part

        if not name:
            self.print_error(
                "Marketplace name required: /plugins marketplace remove <name> [--force]"
            )
            return CommandResult(success=False, message="Name required")

        # Skip confirmation if --force or non-interactive (TUI)
        if not force and self._can_prompt_interactively():
            if not Confirm.ask(f"Remove marketplace '{name}'?"):
                self.print_info("Cancelled")
                return CommandResult(success=False, message="Cancelled")

        try:
            self.plugin_manager.remove_marketplace(name)
            self.print_success(f"Removed marketplace: {name}")
            self.console.print()
            return CommandResult(success=True, message=f"Removed: {name}")
        except MarketplaceNotFoundError as e:
            self.print_error(str(e))
            return CommandResult(success=False, message=str(e))

    def _list_marketplace_plugins(self, name: str) -> CommandResult:
        """List plugins available in a marketplace.

        Args:
            name: Marketplace name

        Returns:
            CommandResult with execution status
        """
        if not name:
            self.print_error("Marketplace name required: /plugins marketplace plugins <name>")
            return CommandResult(success=False, message="Name required")

        try:
            plugins = self.plugin_manager.list_marketplace_plugins(name)

            if not plugins:
                self.print_info(f"No plugins found in marketplace '{name}'")
                self.console.print()
                return CommandResult(success=True)

            table = Table(show_header=True, header_style="bold")
            table.add_column("Name", style="cyan")
            table.add_column("Version")
            table.add_column("Description")
            table.add_column("Skills", style="dim")

            for plugin in plugins:
                desc = (
                    plugin.description[:40] + "..."
                    if len(plugin.description) > 40
                    else plugin.description
                )
                skills = ", ".join(plugin.skills[:3])
                if len(plugin.skills) > 3:
                    skills += f" +{len(plugin.skills) - 3}"
                table.add_row(plugin.name, plugin.version, desc, skills)

            self.console.print(table)
            self.console.print()
            self.print_info(f"Found {len(plugins)} plugin(s) in '{name}'")
            self.console.print()

            return CommandResult(success=True, data=plugins)

        except (MarketplaceNotFoundError, PluginManagerError) as e:
            self.print_error(str(e))
            return CommandResult(success=False, message=str(e))
