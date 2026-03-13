"""Plugin Manager for handling marketplace and plugin operations."""

import json
from pathlib import Path
from typing import Optional

from opendev.core.paths import get_paths
from opendev.core.plugins.manager.bundle import BundleMixin
from opendev.core.plugins.manager.installer import InstallerMixin
from opendev.core.plugins.manager.marketplace import MarketplaceMixin
from opendev.core.plugins.models import PluginMetadata


class PluginManagerError(Exception):
    """Base exception for plugin manager errors."""

    pass


class MarketplaceNotFoundError(PluginManagerError):
    """Marketplace not found error."""

    pass


class PluginNotFoundError(PluginManagerError):
    """Plugin not found error."""

    pass


class BundleNotFoundError(PluginManagerError):
    """Bundle not found error."""

    pass


class PluginManager(MarketplaceMixin, InstallerMixin, BundleMixin):
    """Manager for marketplace and plugin operations."""

    def __init__(self, working_dir: Optional[Path] = None):
        """Initialize plugin manager.

        Args:
            working_dir: Working directory for path resolution
        """
        self.working_dir = working_dir
        self.paths = get_paths(working_dir)

    def _load_plugin_metadata(self, plugin_dir: Path) -> Optional[PluginMetadata]:
        """Load plugin metadata from plugin.json.

        Checks multiple possible locations:
        1. .opendev/plugin.json (consistent with app)
        2. plugin.json (at root)
        3. .swecli/plugin.json (legacy fallback)
        4. .swecli-plugin/plugin.json (legacy fallback)

        Args:
            plugin_dir: Plugin directory

        Returns:
            PluginMetadata or None if invalid
        """
        possible_paths = [
            plugin_dir / ".opendev" / "plugin.json",
            plugin_dir / "plugin.json",
            plugin_dir / ".swecli" / "plugin.json",  # legacy fallback
            plugin_dir / ".swecli-plugin" / "plugin.json",  # legacy fallback
        ]

        metadata_file = None
        for p in possible_paths:
            if p.exists():
                metadata_file = p
                break

        if metadata_file is None:
            return None

        try:
            data = json.loads(metadata_file.read_text(encoding="utf-8"))
            return PluginMetadata.model_validate(data)
        except Exception:
            return None

    def _parse_skill_metadata(self, skill_file: Path) -> tuple[str, str]:
        """Parse SKILL.md for name and description.

        Args:
            skill_file: Path to SKILL.md

        Returns:
            Tuple of (name, description)
        """
        try:
            content = skill_file.read_text(encoding="utf-8")
            name = ""
            description = ""

            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    for line in frontmatter.strip().split("\n"):
                        if line.startswith("name:"):
                            name = line.split(":", 1)[1].strip().strip("\"'")
                        elif line.startswith("description:"):
                            description = line.split(":", 1)[1].strip().strip("\"'")

            return name, description
        except Exception:
            return "", ""

    def _estimate_tokens(self, file_path: Path) -> int:
        """Estimate token count for a file.

        Uses a simple heuristic: ~4 characters per token.

        Args:
            file_path: Path to file

        Returns:
            Estimated token count
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            # Rough estimate: 4 characters per token
            return len(content) // 4
        except Exception:
            return 0
