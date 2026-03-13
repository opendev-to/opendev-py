"""Bundle management mixin for PluginManager."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

from opendev.core.plugins.config import (
    load_direct_plugins,
    save_direct_plugins,
    get_all_direct_plugins,
)
from opendev.core.plugins.models import DirectPlugin

if TYPE_CHECKING:
    pass


class BundleMixin:
    """Bundle management methods. Mixed into PluginManager, not instantiated directly."""

    def list_bundles(
        self, scope: Optional[Literal["user", "project"]] = None
    ) -> list[DirectPlugin]:
        """List installed bundles.

        Args:
            scope: Optional scope filter ('user', 'project', or None for all)

        Returns:
            List of DirectPlugin objects
        """
        if scope:
            bundles = load_direct_plugins(self.working_dir, scope=scope)
            return list(bundles.bundles.values())
        else:
            return get_all_direct_plugins(self.working_dir)

    def _get_bundle(
        self, name: str, scope: Optional[Literal["user", "project"]] = None
    ) -> Optional[DirectPlugin]:
        """Get a specific bundle by name.

        Args:
            name: Bundle name
            scope: Optional scope to search (None = search both)

        Returns:
            DirectPlugin or None if not found
        """
        if scope:
            bundles = load_direct_plugins(self.working_dir, scope=scope)
            return bundles.get(name)
        else:
            # Search project first, then user
            project_bundles = load_direct_plugins(self.working_dir, scope="project")
            if name in project_bundles.bundles:
                return project_bundles.bundles[name]

            user_bundles = load_direct_plugins(self.working_dir, scope="user")
            return user_bundles.get(name)

    def uninstall_bundle(self, name: str) -> None:
        """Uninstall a bundle.

        Args:
            name: Bundle name

        Raises:
            BundleNotFoundError: If bundle isn't installed
        """
        from opendev.core.plugins.manager.manager import BundleNotFoundError

        # Find bundle in either scope
        for scope in ["project", "user"]:
            bundles = load_direct_plugins(self.working_dir, scope=scope)
            bundle = bundles.get(name)

            if bundle:
                # Remove directory
                bundle_path = Path(bundle.path)
                if bundle_path.exists():
                    shutil.rmtree(bundle_path)

                # Remove from registry
                bundles.remove(name)
                save_direct_plugins(bundles, self.working_dir, scope=scope)
                return

        raise BundleNotFoundError(f"Bundle '{name}' not found")

    def sync_bundle(self, name: str) -> None:
        """Sync (git pull) a bundle.

        Args:
            name: Bundle name

        Raises:
            BundleNotFoundError: If bundle doesn't exist
            PluginManagerError: If sync fails
        """
        from opendev.core.plugins.manager.manager import BundleNotFoundError, PluginManagerError

        bundle = self._get_bundle(name)
        if not bundle:
            raise BundleNotFoundError(f"Bundle '{name}' not found")

        bundle_dir = Path(bundle.path)
        if not bundle_dir.exists():
            raise PluginManagerError(f"Bundle directory missing: {bundle_dir}")

        # Git pull
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(bundle_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise PluginManagerError(f"Git pull failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            raise PluginManagerError("Git pull timed out")

    def sync_all_bundles(self) -> dict[str, Optional[str]]:
        """Sync all installed bundles.

        Returns:
            Dict of bundle name to error message (None if successful)
        """
        results = {}
        for bundle in self.list_bundles():
            try:
                self.sync_bundle(bundle.name)
                results[bundle.name] = None
            except Exception as e:
                results[bundle.name] = str(e)
        return results

    def enable_bundle(self, name: str) -> None:
        """Enable a disabled bundle.

        Args:
            name: Bundle name

        Raises:
            BundleNotFoundError: If bundle doesn't exist
        """
        from opendev.core.plugins.manager.manager import BundleNotFoundError

        for scope in ["project", "user"]:
            bundles = load_direct_plugins(self.working_dir, scope=scope)
            bundle = bundles.get(name)
            if bundle:
                bundle.enabled = True
                save_direct_plugins(bundles, self.working_dir, scope=scope)
                return

        raise BundleNotFoundError(f"Bundle '{name}' not found")

    def disable_bundle(self, name: str) -> None:
        """Disable a bundle.

        Args:
            name: Bundle name

        Raises:
            BundleNotFoundError: If bundle doesn't exist
        """
        from opendev.core.plugins.manager.manager import BundleNotFoundError

        for scope in ["project", "user"]:
            bundles = load_direct_plugins(self.working_dir, scope=scope)
            bundle = bundles.get(name)
            if bundle:
                bundle.enabled = False
                save_direct_plugins(bundles, self.working_dir, scope=scope)
                return

        raise BundleNotFoundError(f"Bundle '{name}' not found")
