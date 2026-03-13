"""Marketplace management mixin for PluginManager."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from opendev.core.plugins.config import (
    load_known_marketplaces,
    save_known_marketplaces,
)
from opendev.core.plugins.models import (
    MarketplaceInfo,
    PluginMetadata,
)

if TYPE_CHECKING:
    pass


class MarketplaceMixin:
    """Marketplace management methods. Mixed into PluginManager, not instantiated directly."""

    def add_marketplace(
        self, url: str, name: Optional[str] = None, branch: str = "main"
    ) -> MarketplaceInfo:
        """Add a marketplace by cloning its repository.

        Args:
            url: Git URL of the marketplace repository
            name: Optional name for the marketplace (derived from URL if not provided)
            branch: Git branch to track (default: main)

        Returns:
            MarketplaceInfo for the added marketplace

        Raises:
            PluginManagerError: If cloning fails or marketplace is invalid
        """
        from opendev.core.plugins.manager.manager import PluginManagerError

        # Derive name from URL if not provided
        if not name:
            name = self._extract_name_from_url(url)

        # Check if marketplace already exists
        marketplaces = load_known_marketplaces(self.working_dir)
        if name in marketplaces.marketplaces:
            raise PluginManagerError(
                f"Marketplace '{name}' already exists. Use 'sync' to update it."
            )

        # Prepare target directory
        target_dir = self.paths.global_marketplaces_dir / name
        if target_dir.exists():
            shutil.rmtree(target_dir)

        # Clone repository
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", branch, url, str(target_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise PluginManagerError(f"Git clone failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            raise PluginManagerError("Git clone timed out")
        except FileNotFoundError:
            raise PluginManagerError("Git is not installed or not in PATH")

        # Validate marketplace structure
        if not self._validate_marketplace(target_dir):
            shutil.rmtree(target_dir)
            raise PluginManagerError(
                "Invalid marketplace: no marketplace.json found. "
                "Expected one of: .opendev/marketplace.json, marketplace.json"
            )

        # Register marketplace
        info = MarketplaceInfo(
            name=name,
            url=url,
            branch=branch,
            added_at=datetime.now(),
            last_updated=datetime.now(),
        )
        marketplaces.marketplaces[name] = info
        save_known_marketplaces(marketplaces, self.working_dir)

        return info

    def remove_marketplace(self, name: str) -> None:
        """Remove a marketplace.

        Args:
            name: Marketplace name

        Raises:
            MarketplaceNotFoundError: If marketplace doesn't exist
        """
        from opendev.core.plugins.manager.manager import MarketplaceNotFoundError

        marketplaces = load_known_marketplaces(self.working_dir)
        if name not in marketplaces.marketplaces:
            raise MarketplaceNotFoundError(f"Marketplace '{name}' not found")

        # Remove directory
        marketplace_dir = self.paths.global_marketplaces_dir / name
        if marketplace_dir.exists():
            shutil.rmtree(marketplace_dir)

        # Remove from registry
        del marketplaces.marketplaces[name]
        save_known_marketplaces(marketplaces, self.working_dir)

    def list_marketplaces(self) -> list[MarketplaceInfo]:
        """List all registered marketplaces.

        Returns:
            List of MarketplaceInfo objects
        """
        marketplaces = load_known_marketplaces(self.working_dir)
        return list(marketplaces.marketplaces.values())

    def sync_marketplace(self, name: str) -> None:
        """Sync (git pull) a marketplace.

        Args:
            name: Marketplace name

        Raises:
            MarketplaceNotFoundError: If marketplace doesn't exist
            PluginManagerError: If sync fails
        """
        from opendev.core.plugins.manager.manager import MarketplaceNotFoundError, PluginManagerError

        marketplaces = load_known_marketplaces(self.working_dir)
        if name not in marketplaces.marketplaces:
            raise MarketplaceNotFoundError(f"Marketplace '{name}' not found")

        marketplace_dir = self.paths.global_marketplaces_dir / name
        if not marketplace_dir.exists():
            raise PluginManagerError(f"Marketplace directory missing: {marketplace_dir}")

        # Git pull
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(marketplace_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise PluginManagerError(f"Git pull failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            raise PluginManagerError("Git pull timed out")

        # Update last_updated timestamp
        marketplaces.marketplaces[name].last_updated = datetime.now()
        save_known_marketplaces(marketplaces, self.working_dir)

    def sync_all_marketplaces(self) -> dict[str, Optional[str]]:
        """Sync all registered marketplaces.

        Returns:
            Dict of marketplace name to error message (None if successful)
        """
        results = {}
        for marketplace in self.list_marketplaces():
            try:
                self.sync_marketplace(marketplace.name)
                results[marketplace.name] = None
            except Exception as e:
                results[marketplace.name] = str(e)
        return results

    def get_marketplace_catalog(self, name: str) -> dict:
        """Get the plugin catalog from a marketplace.

        If no marketplace.json exists, auto-discovers plugins from plugins/ directory.

        Args:
            name: Marketplace name

        Returns:
            Catalog dict from marketplace.json or auto-generated

        Raises:
            MarketplaceNotFoundError: If marketplace doesn't exist
        """
        from opendev.core.plugins.manager.manager import MarketplaceNotFoundError

        marketplaces = load_known_marketplaces(self.working_dir)
        if name not in marketplaces.marketplaces:
            raise MarketplaceNotFoundError(f"Marketplace '{name}' not found")

        marketplace_dir = self.paths.global_marketplaces_dir / name
        catalog_path = self._get_marketplace_json_path(marketplace_dir)

        if catalog_path is not None:
            return json.loads(catalog_path.read_text(encoding="utf-8"))

        # Auto-discover plugins from plugins/ or skills/ directories
        return self._auto_discover_catalog(marketplace_dir)

    def _auto_discover_catalog(self, marketplace_dir: Path) -> dict:
        """Auto-discover plugins when no marketplace.json exists.

        Args:
            marketplace_dir: Marketplace directory

        Returns:
            Auto-generated catalog dict
        """
        plugins = []

        # Check plugins/ directory
        plugins_dir = marketplace_dir / "plugins"
        if plugins_dir.exists() and plugins_dir.is_dir():
            for item in plugins_dir.iterdir():
                if item.is_dir():
                    plugins.append(item.name)

        # Check skills/ directory (treat each skill as a single-skill plugin)
        skills_dir = marketplace_dir / "skills"
        if skills_dir.exists() and skills_dir.is_dir():
            for item in skills_dir.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    plugins.append(item.name)

        return {"plugins": plugins, "auto_discovered": True}

    def list_marketplace_plugins(self, name: str) -> list[PluginMetadata]:
        """List all plugins available in a marketplace.

        Args:
            name: Marketplace name

        Returns:
            List of PluginMetadata objects
        """
        catalog = self.get_marketplace_catalog(name)
        plugins = []
        marketplace_dir = self.paths.global_marketplaces_dir / name

        # Check plugins/ directory
        plugins_dir = marketplace_dir / "plugins"
        if plugins_dir.exists():
            for plugin_name in catalog.get("plugins", []):
                plugin_dir = plugins_dir / plugin_name
                if plugin_dir.exists():
                    metadata = self._load_plugin_metadata(plugin_dir)
                    if metadata:
                        plugins.append(metadata)
                    else:
                        # Create metadata from directory if no plugin.json
                        plugins.append(
                            PluginMetadata(
                                name=plugin_name,
                                version="0.0.0",
                                description=f"Plugin: {plugin_name}",
                                skills=self._discover_skills_in_dir(plugin_dir),
                            )
                        )

        # Check skills/ directory (each skill is treated as a plugin)
        skills_dir = marketplace_dir / "skills"
        if skills_dir.exists() and catalog.get("auto_discovered"):
            for skill_name in catalog.get("plugins", []):
                skill_dir = skills_dir / skill_name
                if skill_dir.exists() and (skill_dir / "SKILL.md").exists():
                    # Already listed from plugins/ check above? Skip duplicate
                    if any(p.name == skill_name for p in plugins):
                        continue
                    name_from_skill, desc = self._parse_skill_metadata(skill_dir / "SKILL.md")
                    plugins.append(
                        PluginMetadata(
                            name=skill_name,
                            version="0.0.0",
                            description=desc or f"Skill: {skill_name}",
                            skills=[skill_name],
                        )
                    )

        return plugins

    def _validate_marketplace(self, directory: Path) -> bool:
        """Validate marketplace directory structure.

        Checks multiple possible locations for marketplace.json:
        1. .opendev/marketplace.json (consistent with app)
        2. marketplace.json (at root)
        3. .swecli/marketplace.json (legacy fallback)
        4. .swecli-marketplace/marketplace.json (legacy fallback)

        Also accepts repos with plugins/ or skills/ directories (auto-discovery mode).

        Args:
            directory: Marketplace directory

        Returns:
            True if valid, False otherwise
        """
        # Check for marketplace.json
        possible_paths = [
            directory / ".opendev" / "marketplace.json",
            directory / "marketplace.json",
            directory / ".swecli" / "marketplace.json",  # legacy fallback
            directory / ".swecli-marketplace" / "marketplace.json",  # legacy fallback
        ]
        if any(p.exists() for p in possible_paths):
            return True

        # Auto-discovery: accept if plugins/ or skills/ directory exists
        plugins_dir = directory / "plugins"
        skills_dir = directory / "skills"
        if plugins_dir.exists() and plugins_dir.is_dir():
            return True
        if skills_dir.exists() and skills_dir.is_dir():
            return True

        return False

    def _get_marketplace_json_path(self, directory: Path) -> Optional[Path]:
        """Find the marketplace.json file in a marketplace directory.

        Args:
            directory: Marketplace directory

        Returns:
            Path to marketplace.json or None if not found
        """
        possible_paths = [
            directory / ".opendev" / "marketplace.json",
            directory / "marketplace.json",
            directory / ".swecli" / "marketplace.json",  # legacy fallback
            directory / ".swecli-marketplace" / "marketplace.json",  # legacy fallback
        ]
        for p in possible_paths:
            if p.exists():
                return p
        return None
