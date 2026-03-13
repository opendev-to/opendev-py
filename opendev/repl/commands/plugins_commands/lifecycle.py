"""Lifecycle subcommands for plugins (list/enable/disable)."""

from rich.table import Table

from opendev.repl.commands.base import CommandResult
from opendev.core.plugins import (
    PluginNotFoundError,
    BundleNotFoundError,
)


class LifecycleCommandsMixin:
    """Mixin for plugin lifecycle commands."""

    def _list_plugins(self) -> CommandResult:
        """List installed plugins and bundles.

        Returns:
            CommandResult with execution status
        """
        plugins = self.plugin_manager.list_installed()
        bundles = self.plugin_manager.list_bundles()

        if not plugins and not bundles:
            self.print_info("No plugins or bundles installed.")
            self.print_continuation("Install with: /plugins install <url>")
            self.console.print()
            return CommandResult(success=True)

        # Show bundles first (URL installs)
        if bundles:
            table = Table(show_header=True, header_style="bold")
            table.add_column("Name", style="cyan")
            table.add_column("URL")
            table.add_column("Scope", style="dim")
            table.add_column("Status")

            for bundle in bundles:
                status = "[green]enabled[/green]" if bundle.enabled else "[dim]disabled[/dim]"
                # Truncate URL for display
                url = bundle.url
                if len(url) > 40:
                    url = url[:37] + "..."
                table.add_row(
                    bundle.name,
                    url,
                    bundle.scope,
                    status,
                )

            self.console.print(table)
            self.console.print()

        # Show marketplace plugins
        if plugins:
            self.print_line("[bold]Marketplace Plugins:[/bold]")
            table = Table(show_header=True, header_style="bold")
            table.add_column("Plugin", style="cyan")
            table.add_column("Version")
            table.add_column("Marketplace")
            table.add_column("Scope", style="dim")
            table.add_column("Status")

            for plugin in plugins:
                status = "[green]enabled[/green]" if plugin.enabled else "[dim]disabled[/dim]"
                table.add_row(
                    plugin.name,
                    plugin.version,
                    plugin.marketplace,
                    plugin.scope,
                    status,
                )

            self.console.print(table)
            self.console.print()

        return CommandResult(success=True, data={"plugins": plugins, "bundles": bundles})

    def _enable_plugin(self, spec: str) -> CommandResult:
        """Enable a plugin or bundle.

        Args:
            spec: Plugin spec (<plugin>@<marketplace>) or bundle name

        Returns:
            CommandResult with execution status
        """
        if not spec:
            self.print_error(
                "Usage: /plugins enable <name> or /plugins enable <plugin>@<marketplace>"
            )
            return CommandResult(success=False, message="Name required")

        # Check if it's a bundle (no @ in spec)
        if "@" not in spec:
            try:
                self.plugin_manager.enable_bundle(spec)
                self.print_success(f"Enabled bundle: {spec}")
                self.console.print()
                return CommandResult(success=True, message=f"Enabled: {spec}")
            except BundleNotFoundError:
                self.print_error(f"Bundle '{spec}' not found")
                return CommandResult(success=False, message="Bundle not found")

        # Traditional marketplace plugin
        plugin_name, marketplace = spec.rsplit("@", 1)

        for scope in ["project", "user"]:
            try:
                self.plugin_manager.enable_plugin(plugin_name, marketplace, scope=scope)
                self.print_success(f"Enabled: {plugin_name}")
                self.console.print()
                return CommandResult(success=True, message=f"Enabled: {plugin_name}")
            except PluginNotFoundError:
                continue

        self.print_error(f"Plugin '{plugin_name}' not found in any scope")
        return CommandResult(success=False, message="Plugin not found")

    def _disable_plugin(self, spec: str) -> CommandResult:
        """Disable a plugin or bundle.

        Args:
            spec: Plugin spec (<plugin>@<marketplace>) or bundle name

        Returns:
            CommandResult with execution status
        """
        if not spec:
            self.print_error(
                "Usage: /plugins disable <name> or /plugins disable <plugin>@<marketplace>"
            )
            return CommandResult(success=False, message="Name required")

        # Check if it's a bundle (no @ in spec)
        if "@" not in spec:
            try:
                self.plugin_manager.disable_bundle(spec)
                self.print_success(f"Disabled bundle: {spec}")
                self.console.print()
                return CommandResult(success=True, message=f"Disabled: {spec}")
            except BundleNotFoundError:
                self.print_error(f"Bundle '{spec}' not found")
                return CommandResult(success=False, message="Bundle not found")

        # Traditional marketplace plugin
        plugin_name, marketplace = spec.rsplit("@", 1)

        for scope in ["project", "user"]:
            try:
                self.plugin_manager.disable_plugin(plugin_name, marketplace, scope=scope)
                self.print_success(f"Disabled: {plugin_name}")
                self.console.print()
                return CommandResult(success=True, message=f"Disabled: {plugin_name}")
            except PluginNotFoundError:
                continue

        self.print_error(f"Plugin '{plugin_name}' not found in any scope")
        return CommandResult(success=False, message="Plugin not found")
