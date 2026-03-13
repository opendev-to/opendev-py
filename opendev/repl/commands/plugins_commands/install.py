"""Install/uninstall subcommands for plugins."""

from rich.prompt import Prompt, Confirm

from opendev.repl.commands.base import CommandResult
from opendev.core.plugins import (
    PluginManagerError,
    MarketplaceNotFoundError,
    PluginNotFoundError,
    BundleNotFoundError,
)
from opendev.ui_textual.components.plugin_panels import create_scope_selection_panel


class InstallCommandsMixin:
    """Mixin for install/uninstall/sync/update commands."""

    def _install_plugin(self, spec: str) -> CommandResult:
        """Install a plugin from URL or marketplace.

        Args:
            spec: Either a URL or plugin spec in format <plugin>@<marketplace>

        Returns:
            CommandResult with execution status
        """
        if not spec:
            self.print_error(
                "Usage: /plugins install <url> or /plugins install <plugin>@<marketplace>"
            )
            return CommandResult(success=False, message="Spec required")

        # Check if it's a URL (direct bundle install)
        if spec.startswith(("http://", "https://", "git@")):
            return self._install_from_url(spec)

        # Traditional marketplace install
        if "@" not in spec:
            self.print_error(
                "Usage: /plugins install <url> or /plugins install <plugin>@<marketplace>"
            )
            return CommandResult(success=False, message="Invalid spec")

        plugin_name, marketplace = spec.rsplit("@", 1)

        # Ask for scope with styled panel
        panel = create_scope_selection_panel(0, str(self.config_manager.working_dir))
        self.console.print(panel)

        choice = Prompt.ask("Select", choices=["1", "2"], default="1")
        scope = "user" if choice == "1" else "project"

        self.print_command_header("Installing plugin", f"{plugin_name} from {marketplace}")

        try:
            installed = self.plugin_manager.install_plugin(plugin_name, marketplace, scope=scope)
            self.print_success(f"Installed: [cyan]{installed.name}[/cyan] v{installed.version}")
            self.print_continuation(f"Scope: {scope}")
            self.print_continuation(f"Path: {installed.path}")
            self.console.print()

            # Show installed skills
            skills = self.plugin_manager.get_plugin_skills()
            plugin_skills = [s for s in skills if s.plugin_name == plugin_name]
            if plugin_skills:
                self.print_info(f"Available skills ({len(plugin_skills)}):")
                for skill in plugin_skills:
                    self.print_continuation(f"  - {skill.display_name}")
                self.console.print()

            return CommandResult(success=True, message=f"Installed: {plugin_name}", data=installed)

        except (MarketplaceNotFoundError, PluginNotFoundError, PluginManagerError) as e:
            self.print_error(str(e))
            return CommandResult(success=False, message=str(e))

    def _install_from_url(self, args: str) -> CommandResult:
        """Install plugin bundle directly from URL.

        Supports:
        - /plugins install <url>
        - /plugins install <url> --project
        - /plugins install <url> --name=custom-name

        Args:
            args: URL and optional flags

        Returns:
            CommandResult with execution status
        """
        parts = args.split()
        url = parts[0]
        scope = "user"  # Default to user scope
        name = None

        for part in parts[1:]:
            if part == "--project":
                scope = "project"
            elif part.startswith("--name="):
                name = part.split("=", 1)[1]

        self.print_command_header("Installing from URL", url)

        try:
            bundle = self.plugin_manager.install_from_url(url, scope=scope, name=name)
            self.print_success(f"Installed: [cyan]{bundle.name}[/cyan]")
            self.print_continuation(f"Scope: {scope}")
            self.print_continuation(f"Path: {bundle.path}")
            self.console.print()

            # Show available skills from the bundle
            skills = self.plugin_manager.get_plugin_skills()
            bundle_skills = [s for s in skills if s.bundle_name == bundle.name]
            if bundle_skills:
                self.print_info(f"Available skills ({len(bundle_skills)}):")
                for skill in bundle_skills[:10]:
                    desc = (
                        skill.description[:50] + "..."
                        if len(skill.description) > 50
                        else skill.description
                    )
                    self.print_continuation(f"  - [cyan]{skill.display_name}[/cyan]: {desc}")
                if len(bundle_skills) > 10:
                    self.print_continuation(f"  ... and {len(bundle_skills) - 10} more")
                self.console.print()

            return CommandResult(success=True, message=f"Installed: {bundle.name}", data=bundle)

        except PluginManagerError as e:
            self.print_error(str(e))
            return CommandResult(success=False, message=str(e))

    def _uninstall_plugin(self, args: str) -> CommandResult:
        """Uninstall a plugin or bundle.

        Args:
            args: Plugin spec (<plugin>@<marketplace>) or bundle name, with optional --force/-f

        Returns:
            CommandResult with execution status
        """
        # Parse --force flag
        parts = args.split()
        spec = ""
        force = False
        for part in parts:
            if part in ("--force", "-f"):
                force = True
            elif not spec:
                spec = part

        if not spec:
            self.print_error(
                "Usage: /plugins uninstall <name> [--force] or "
                "/plugins uninstall <plugin>@<marketplace> [--force]"
            )
            return CommandResult(success=False, message="Name required")

        # Check if it's a bundle (no @ in spec)
        if "@" not in spec:
            return self._uninstall_bundle(spec, force=force)

        # Traditional marketplace plugin uninstall
        plugin_name, marketplace = spec.rsplit("@", 1)

        # Skip confirmation if --force or non-interactive (TUI)
        if not force and self._can_prompt_interactively():
            if not Confirm.ask(f"Uninstall plugin '{plugin_name}' from '{marketplace}'?"):
                self.print_info("Cancelled")
                return CommandResult(success=False, message="Cancelled")

        # Try both scopes
        for scope in ["project", "user"]:
            try:
                self.plugin_manager.uninstall_plugin(plugin_name, marketplace, scope=scope)
                self.print_success(f"Uninstalled: {plugin_name} ({scope} scope)")
                self.console.print()
                return CommandResult(success=True, message=f"Uninstalled: {plugin_name}")
            except PluginNotFoundError:
                continue

        self.print_error(f"Plugin '{plugin_name}' not found in any scope")
        return CommandResult(success=False, message="Plugin not found")

    def _uninstall_bundle(self, name: str, force: bool = False) -> CommandResult:
        """Uninstall a bundle.

        Args:
            name: Bundle name
            force: Skip confirmation prompt

        Returns:
            CommandResult with execution status
        """
        # Skip confirmation if --force or non-interactive (TUI)
        if not force and self._can_prompt_interactively():
            if not Confirm.ask(f"Uninstall bundle '{name}'?"):
                self.print_info("Cancelled")
                return CommandResult(success=False, message="Cancelled")

        try:
            self.plugin_manager.uninstall_bundle(name)
            self.print_success(f"Uninstalled: {name}")
            self.console.print()
            return CommandResult(success=True, message=f"Uninstalled: {name}")
        except BundleNotFoundError:
            self.print_error(f"Bundle '{name}' not found")
            return CommandResult(success=False, message="Bundle not found")
        except PluginManagerError as e:
            self.print_error(str(e))
            return CommandResult(success=False, message=str(e))

    def _sync_plugin(self, name: str) -> CommandResult:
        """Sync/update a plugin or bundle.

        Args:
            name: Plugin name, bundle name, or empty for all

        Returns:
            CommandResult with execution status
        """
        if not name:
            # Sync all bundles and marketplaces
            self.print_command_header("Syncing all plugins and bundles")

            # Sync bundles
            bundle_results = self.plugin_manager.sync_all_bundles()
            for bundle_name, error in bundle_results.items():
                if error:
                    self.print_error(f"Bundle {bundle_name}: {error}")
                else:
                    self.print_success(f"Bundle {bundle_name}: synced")

            # Sync marketplaces
            mp_results = self.plugin_manager.sync_all_marketplaces()
            for mp_name, error in mp_results.items():
                if error:
                    self.print_error(f"Marketplace {mp_name}: {error}")
                else:
                    self.print_success(f"Marketplace {mp_name}: synced")

            total = len(bundle_results) + len(mp_results)
            success_count = sum(1 for v in bundle_results.values() if v is None)
            success_count += sum(1 for v in mp_results.values() if v is None)

            self.console.print()
            self.print_info(f"Synced {success_count}/{total}")
            self.console.print()

            return CommandResult(
                success=True,
                message=f"Synced {success_count}/{total}",
            )

        # Try to sync as bundle first
        try:
            self.plugin_manager.sync_bundle(name)
            self.print_success(f"Synced bundle: {name}")
            self.console.print()
            return CommandResult(success=True, message=f"Synced: {name}")
        except BundleNotFoundError:
            pass

        # Try to sync as marketplace
        try:
            self.plugin_manager.sync_marketplace(name)
            self.print_success(f"Synced marketplace: {name}")
            self.console.print()
            return CommandResult(success=True, message=f"Synced: {name}")
        except MarketplaceNotFoundError:
            pass

        self.print_error(f"'{name}' not found as bundle or marketplace")
        return CommandResult(success=False, message="Not found")

    def _update_plugin(self, spec: str) -> CommandResult:
        """Update a plugin.

        Args:
            spec: Plugin spec in format <plugin>@<marketplace>

        Returns:
            CommandResult with execution status
        """
        if not spec or "@" not in spec:
            self.print_error("Plugin spec required: /plugins update <plugin>@<marketplace>")
            return CommandResult(success=False, message="Invalid spec")

        plugin_name, marketplace = spec.rsplit("@", 1)

        self.print_command_header("Updating plugin", plugin_name)

        # Try both scopes
        for scope in ["project", "user"]:
            try:
                installed = self.plugin_manager.update_plugin(
                    plugin_name, marketplace, scope=scope
                )
                self.print_success(
                    f"Updated: [cyan]{installed.name}[/cyan] v{installed.version}"
                )
                self.console.print()
                return CommandResult(
                    success=True, message=f"Updated: {plugin_name}", data=installed
                )
            except PluginNotFoundError:
                continue
            except PluginManagerError as e:
                self.print_error(str(e))
                return CommandResult(success=False, message=str(e))

        self.print_error(f"Plugin '{plugin_name}' not found in any scope")
        return CommandResult(success=False, message="Plugin not found")
