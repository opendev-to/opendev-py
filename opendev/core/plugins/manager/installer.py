"""Plugin installation mixin for PluginManager."""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional
from urllib.parse import urlparse

from opendev.core.plugins.config import (
    load_known_marketplaces,
    load_installed_plugins,
    save_installed_plugins,
    get_all_installed_plugins,
    load_direct_plugins,
    save_direct_plugins,
)
from opendev.core.plugins.models import (
    InstalledPlugin,
    SkillMetadata,
    DirectPlugin,
)

if TYPE_CHECKING:
    pass


class InstallerMixin:
    """Plugin install/uninstall methods. Mixed into PluginManager, not instantiated directly."""

    def install_plugin(
        self,
        plugin_name: str,
        marketplace: str,
        scope: Literal["user", "project"] = "user",
        version: Optional[str] = None,
    ) -> InstalledPlugin:
        """Install a plugin from a marketplace.

        Args:
            plugin_name: Plugin name
            marketplace: Marketplace name
            scope: Installation scope ('user' or 'project')
            version: Specific version (default: latest)

        Returns:
            InstalledPlugin for the installed plugin

        Raises:
            PluginNotFoundError: If plugin doesn't exist in marketplace
            PluginManagerError: If installation fails
        """
        from opendev.core.plugins.manager.manager import (
            MarketplaceNotFoundError,
            PluginNotFoundError,
            PluginManagerError,
        )

        # Verify marketplace exists
        marketplaces = load_known_marketplaces(self.working_dir)
        if marketplace not in marketplaces.marketplaces:
            raise MarketplaceNotFoundError(f"Marketplace '{marketplace}' not found")

        marketplace_dir = self.paths.global_marketplaces_dir / marketplace

        # Find plugin in marketplace - check plugins/ first, then skills/
        source_dir = marketplace_dir / "plugins" / plugin_name
        is_skill_as_plugin = False

        if not source_dir.exists():
            # Check if it's a skill in the skills/ directory
            skill_dir = marketplace_dir / "skills" / plugin_name
            if skill_dir.exists() and (skill_dir / "SKILL.md").exists():
                source_dir = skill_dir
                is_skill_as_plugin = True
            else:
                raise PluginNotFoundError(f"Plugin '{plugin_name}' not found in '{marketplace}'")

        # Load plugin metadata
        metadata = self._load_plugin_metadata(source_dir)
        if not metadata and not is_skill_as_plugin:
            # For regular plugins, metadata is required
            raise PluginManagerError(f"Invalid plugin: missing plugin.json")

        if is_skill_as_plugin:
            # Create metadata for skill-as-plugin
            skill_name, skill_desc = self._parse_skill_metadata(source_dir / "SKILL.md")
            plugin_version = version or "0.0.0"
        else:
            plugin_version = version or metadata.version

        # Determine target directory based on scope
        if scope == "project":
            cache_dir = self.paths.project_plugins_dir / "cache"
        else:
            cache_dir = self.paths.global_plugin_cache_dir

        target_dir = cache_dir / marketplace / plugin_name / plugin_version

        # Copy plugin to cache
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

        # Register installation
        installed = InstalledPlugin(
            name=plugin_name,
            marketplace=marketplace,
            version=plugin_version,
            scope=scope,
            path=str(target_dir),
            enabled=True,
            installed_at=datetime.now(),
        )

        plugins = load_installed_plugins(self.working_dir, scope=scope)
        plugins.add(installed)
        save_installed_plugins(plugins, self.working_dir, scope=scope)

        return installed

    def uninstall_plugin(
        self, plugin_name: str, marketplace: str, scope: Literal["user", "project"] = "user"
    ) -> None:
        """Uninstall a plugin.

        Args:
            plugin_name: Plugin name
            marketplace: Marketplace name
            scope: Installation scope

        Raises:
            PluginNotFoundError: If plugin isn't installed
        """
        from opendev.core.plugins.manager.manager import PluginNotFoundError

        plugins = load_installed_plugins(self.working_dir, scope=scope)
        plugin = plugins.get(marketplace, plugin_name)

        if not plugin:
            raise PluginNotFoundError(
                f"Plugin '{marketplace}:{plugin_name}' not installed in {scope} scope"
            )

        # Remove from cache
        plugin_path = Path(plugin.path)
        if plugin_path.exists():
            shutil.rmtree(plugin_path)

        # Remove from registry
        plugins.remove(marketplace, plugin_name)
        save_installed_plugins(plugins, self.working_dir, scope=scope)

    def update_plugin(
        self, plugin_name: str, marketplace: str, scope: Literal["user", "project"] = "user"
    ) -> InstalledPlugin:
        """Update a plugin to the latest version.

        Args:
            plugin_name: Plugin name
            marketplace: Marketplace name
            scope: Installation scope

        Returns:
            Updated InstalledPlugin

        Raises:
            PluginNotFoundError: If plugin isn't installed
        """
        from opendev.core.plugins.manager.manager import PluginNotFoundError

        plugins = load_installed_plugins(self.working_dir, scope=scope)
        plugin = plugins.get(marketplace, plugin_name)

        if not plugin:
            raise PluginNotFoundError(
                f"Plugin '{marketplace}:{plugin_name}' not installed in {scope} scope"
            )

        # Sync marketplace first
        self.sync_marketplace(marketplace)

        # Reinstall (will get latest version)
        return self.install_plugin(plugin_name, marketplace, scope=scope)

    def list_installed(
        self, scope: Optional[Literal["user", "project"]] = None
    ) -> list[InstalledPlugin]:
        """List installed plugins.

        Args:
            scope: Optional scope filter ('user', 'project', or None for all)

        Returns:
            List of InstalledPlugin objects
        """
        if scope:
            plugins = load_installed_plugins(self.working_dir, scope=scope)
            return list(plugins.plugins.values())
        else:
            return get_all_installed_plugins(self.working_dir)

    def enable_plugin(
        self, plugin_name: str, marketplace: str, scope: Literal["user", "project"] = "user"
    ) -> None:
        """Enable a disabled plugin.

        Args:
            plugin_name: Plugin name
            marketplace: Marketplace name
            scope: Installation scope
        """
        from opendev.core.plugins.manager.manager import PluginNotFoundError

        plugins = load_installed_plugins(self.working_dir, scope=scope)
        plugin = plugins.get(marketplace, plugin_name)

        if not plugin:
            raise PluginNotFoundError(
                f"Plugin '{marketplace}:{plugin_name}' not installed in {scope} scope"
            )

        plugin.enabled = True
        save_installed_plugins(plugins, self.working_dir, scope=scope)

    def disable_plugin(
        self, plugin_name: str, marketplace: str, scope: Literal["user", "project"] = "user"
    ) -> None:
        """Disable a plugin.

        Args:
            plugin_name: Plugin name
            marketplace: Marketplace name
            scope: Installation scope
        """
        from opendev.core.plugins.manager.manager import PluginNotFoundError

        plugins = load_installed_plugins(self.working_dir, scope=scope)
        plugin = plugins.get(marketplace, plugin_name)

        if not plugin:
            raise PluginNotFoundError(
                f"Plugin '{marketplace}:{plugin_name}' not installed in {scope} scope"
            )

        plugin.enabled = False
        save_installed_plugins(plugins, self.working_dir, scope=scope)

    def get_plugin_skills(self) -> list[SkillMetadata]:
        """Get all skills from installed plugins and bundles.

        Returns:
            List of SkillMetadata objects for plugin and bundle skills
        """
        skills = []

        # Skills from marketplace plugins
        for plugin in self.list_installed():
            if not plugin.enabled:
                continue

            plugin_path = Path(plugin.path)
            skills_dir = plugin_path / "skills"

            if not skills_dir.exists():
                continue

            for skill_dir in skills_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue

                name, description = self._parse_skill_metadata(skill_file)
                if not name:
                    name = skill_dir.name

                # Calculate token count
                token_count = self._estimate_tokens(skill_file)

                skills.append(
                    SkillMetadata(
                        name=name,
                        description=description,
                        source="plugin",
                        plugin_name=plugin.name,
                        path=skill_file,
                        token_count=token_count,
                    )
                )

        # Skills from direct bundles (URL installs)
        for bundle in self.list_bundles():
            if not bundle.enabled:
                continue

            bundle_path = Path(bundle.path)
            skills_dir = bundle_path / "skills"

            if not skills_dir.exists():
                continue

            for skill_dir in skills_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue

                name, description = self._parse_skill_metadata(skill_file)
                if not name:
                    name = skill_dir.name

                # Calculate token count
                token_count = self._estimate_tokens(skill_file)

                skills.append(
                    SkillMetadata(
                        name=name,
                        description=description,
                        source="bundle",
                        bundle_name=bundle.name,
                        path=skill_file,
                        token_count=token_count,
                    )
                )

        return skills

    def install_from_url(
        self,
        url: str,
        scope: Literal["user", "project"] = "user",
        name: Optional[str] = None,
        branch: str = "main",
    ) -> DirectPlugin:
        """Install a plugin bundle directly from URL.

        This method auto-detects the repository type:
        - If skills/ exists at root with SKILL.md files, treat as direct bundle
        - Otherwise, provide guidance to use marketplace workflow

        Args:
            url: Git URL of the repository
            scope: Installation scope ('user' or 'project')
            name: Optional name for the bundle (derived from URL if not provided)
            branch: Git branch to track (default: main)

        Returns:
            DirectPlugin for the installed bundle

        Raises:
            PluginManagerError: If installation fails or repo is a marketplace
        """
        from opendev.core.plugins.manager.manager import PluginManagerError

        # Derive name from URL if not provided
        if not name:
            name = self._extract_name_from_url(url)

        # Check if bundle already exists
        existing = self._get_bundle(name, scope)
        if existing:
            raise PluginManagerError(f"Bundle '{name}' already installed. Use 'sync' to update it.")

        # Create temp directory for cloning
        import tempfile

        temp_dir = Path(tempfile.mkdtemp())

        try:
            # Clone repository
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", branch, url, str(temp_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise PluginManagerError(f"Git clone failed: {result.stderr}")

            # Detect repo type
            repo_type = self._detect_repo_type(temp_dir)

            if repo_type == "marketplace":
                # Clean up temp dir
                shutil.rmtree(temp_dir)
                raise PluginManagerError(
                    f"This repository appears to be a marketplace (has plugins/ directory).\n"
                    f"Use the marketplace workflow instead:\n"
                    f"  /plugins marketplace add {url}\n"
                    f"  /plugins install <plugin>@{name}"
                )

            # Move to bundles directory
            if scope == "project":
                bundles_dir = self.paths.project_bundles_dir
            else:
                bundles_dir = self.paths.global_bundles_dir

            target_dir = bundles_dir / name
            if target_dir.exists():
                shutil.rmtree(target_dir)

            bundles_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_dir), str(target_dir))

            # Register bundle
            bundle = DirectPlugin(
                name=name,
                url=url,
                branch=branch,
                scope=scope,
                path=str(target_dir),
                enabled=True,
                installed_at=datetime.now(),
            )

            bundles = load_direct_plugins(self.working_dir, scope=scope)
            bundles.add(bundle)
            save_direct_plugins(bundles, self.working_dir, scope=scope)

            return bundle

        except subprocess.TimeoutExpired:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise PluginManagerError("Git clone timed out")
        except FileNotFoundError:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise PluginManagerError("Git is not installed or not in PATH")
        except PluginManagerError:
            raise
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise PluginManagerError(f"Installation failed: {e}")

    def _detect_repo_type(self, directory: Path) -> Literal["direct", "marketplace"]:
        """Detect if a repository is a direct bundle or marketplace.

        A direct bundle has skills/ at root with SKILL.md files.
        A marketplace has plugins/ directory or marketplace.json.

        Args:
            directory: Repository directory to check

        Returns:
            'direct' if skills bundle, 'marketplace' if marketplace repo
        """
        # Check for marketplace indicators
        plugins_dir = directory / "plugins"
        if plugins_dir.exists() and plugins_dir.is_dir():
            return "marketplace"

        marketplace_paths = [
            directory / ".opendev" / "marketplace.json",
            directory / "marketplace.json",
            directory / ".swecli" / "marketplace.json",  # legacy fallback
            directory / ".swecli-marketplace" / "marketplace.json",  # legacy fallback
        ]
        if any(p.exists() for p in marketplace_paths):
            return "marketplace"

        # Check for direct bundle (skills/ at root with SKILL.md files)
        skills_dir = directory / "skills"
        if skills_dir.exists() and skills_dir.is_dir():
            # Verify at least one SKILL.md exists
            for item in skills_dir.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    return "direct"

        # Default to direct (treat unknown repos as potential skill bundles)
        return "direct"

    def _discover_skills_in_dir(self, plugin_dir: Path) -> list[str]:
        """Discover skill names in a plugin directory.

        Args:
            plugin_dir: Plugin directory path

        Returns:
            List of skill names
        """
        skills = []
        skills_dir = plugin_dir / "skills"
        if skills_dir.exists():
            for item in skills_dir.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    skills.append(item.name)
        return skills

    def _extract_name_from_url(self, url: str) -> str:
        """Extract marketplace name from URL.

        Args:
            url: Git URL

        Returns:
            Derived name
        """
        # Handle various URL formats
        # https://github.com/user/swecli-marketplace
        # git@github.com:user/swecli-marketplace.git

        # Remove .git suffix
        url = re.sub(r"\.git$", "", url)

        # Extract repo name
        parsed = urlparse(url)
        if parsed.path:
            parts = parsed.path.strip("/").split("/")
            if parts:
                name = parts[-1]
                # Remove common prefixes/suffixes
                name = re.sub(r"^swecli-", "", name)
                name = re.sub(r"-marketplace$", "", name)
                return name or "default"

        # Handle SSH-style URLs
        if "@" in url and ":" in url:
            parts = url.split(":")[-1].strip("/").split("/")
            if parts:
                name = parts[-1]
                name = re.sub(r"^swecli-", "", name)
                name = re.sub(r"-marketplace$", "", name)
                return name or "default"

        return "default"
