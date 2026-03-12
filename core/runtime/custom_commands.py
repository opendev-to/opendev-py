"""Custom commands loaded from .opendev/commands/ directory.

Text files in the commands directory become slash commands. Supports:
- $1, $2, etc. for positional arguments
- $ARGUMENTS for all arguments
- $FILE for the current file context

Example:
  .opendev/commands/review.md contains:
    Review this code for: $ARGUMENTS
    Focus on security and performance.

  User types: /review auth module
  Expands to: Review this code for: auth module
              Focus on security and performance.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CustomCommand:
    """A custom command loaded from a text file."""

    def __init__(self, name: str, template: str, source: str, description: str = ""):
        self.name = name
        self.template = template
        self.source = source
        self.description = description or f"Custom command from {source}"

    def expand(self, arguments: str = "", context: dict | None = None) -> str:
        """Expand the template with the given arguments.

        Args:
            arguments: The full argument string after the command name.
            context: Optional context dict with keys like "file".

        Returns:
            Expanded template string.
        """
        result = self.template

        # Replace $ARGUMENTS with the full argument string
        result = result.replace("$ARGUMENTS", arguments)

        # Replace positional $1, $2, etc.
        parts = arguments.split() if arguments else []
        for i, part in enumerate(parts, 1):
            result = result.replace(f"${i}", part)

        # Clean up unreplaced positional args
        result = re.sub(r"\$\d+", "", result)

        # Replace context variables
        if context:
            for key, value in context.items():
                result = result.replace(f"${key.upper()}", str(value))

        return result.strip()


class CustomCommandLoader:
    """Loads and manages custom commands from command directories."""

    def __init__(self, working_dir: Path):
        self._working_dir = working_dir
        self._commands: dict[str, CustomCommand] | None = None

    def _get_command_dirs(self) -> list[tuple[Path, str]]:
        """Get command directories in priority order.

        Returns:
            List of (path, source) tuples.
        """
        dirs = []
        # Project-local commands (highest priority)
        local = self._working_dir / ".opendev" / "commands"
        if local.exists() and local.is_dir():
            dirs.append((local, "project"))

        # User-global commands
        global_dir = Path.home() / ".opendev" / "commands"
        if global_dir.exists() and global_dir.is_dir():
            dirs.append((global_dir, "global"))

        return dirs

    def load_commands(self) -> dict[str, CustomCommand]:
        """Load all custom commands from command directories.

        Returns:
            Dict mapping command name to CustomCommand.
        """
        if self._commands is not None:
            return self._commands

        self._commands = {}
        for cmd_dir, source in self._get_command_dirs():
            for path in sorted(cmd_dir.iterdir()):
                if path.is_file() and path.suffix in (".md", ".txt", ""):
                    name = path.stem
                    if name.startswith(".") or name.startswith("_"):
                        continue
                    try:
                        template = path.read_text(encoding="utf-8")
                        # Extract description from first line if it starts with #
                        description = ""
                        lines = template.strip().split("\n")
                        if lines and lines[0].startswith("#"):
                            description = lines[0].lstrip("# ").strip()

                        self._commands[name] = CustomCommand(
                            name=name,
                            template=template,
                            source=f"{source}:{path.name}",
                            description=description,
                        )
                    except Exception:
                        logger.debug("Failed to load command %s", path, exc_info=True)

        if self._commands:
            logger.debug(
                "Loaded %d custom commands: %s",
                len(self._commands),
                ", ".join(self._commands.keys()),
            )
        return self._commands

    def get_command(self, name: str) -> CustomCommand | None:
        """Get a custom command by name."""
        return self.load_commands().get(name)

    def list_commands(self) -> list[dict]:
        """List all available custom commands.

        Returns:
            List of dicts with name, description, source.
        """
        return [
            {
                "name": cmd.name,
                "description": cmd.description,
                "source": cmd.source,
            }
            for cmd in self.load_commands().values()
        ]

    def reload(self) -> None:
        """Force reload of custom commands."""
        self._commands = None
