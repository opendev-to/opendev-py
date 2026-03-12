"""Security checks for bash command execution."""

import re
import shlex


class SecurityMixin:
    """Mixin providing command safety validation.

    Expects the composing class to have a ``config`` attribute
    (``AppConfig``) with permission settings.
    """

    def _needs_auto_confirm(self, command: str) -> bool:
        """Check if command likely requires interactive confirmation.

        Args:
            command: The command string to check

        Returns:
            True if command matches known interactive patterns
        """
        from opendev.core.context_engineering.tools.implementations.bash_tool.tool import (
            INTERACTIVE_COMMANDS,
        )

        for pattern in INTERACTIVE_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                return True
        return False

    def _is_command_allowed(self, command: str) -> bool:
        """Check if command is in the allowed list.

        Args:
            command: Command to check

        Returns:
            True if command is allowed
        """
        from opendev.core.context_engineering.tools.implementations.bash_tool.tool import (
            SAFE_COMMANDS,
        )

        # Get the base command (first word)
        base_command = command.strip().split()[0] if command.strip() else ""

        # Check if it's in safe commands
        if base_command in SAFE_COMMANDS:
            return True

        # Check against permission patterns
        return self.config.permissions.bash.is_allowed(command)

    def _is_dangerous(self, command: str) -> bool:
        """Check if command matches dangerous patterns.

        Args:
            command: Command to check

        Returns:
            True if command is dangerous
        """
        from opendev.core.context_engineering.tools.implementations.bash_tool.tool import (
            DANGEROUS_PATTERNS,
        )

        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True

        # Check config deny patterns
        for pattern in self.config.permissions.bash.compiled_patterns:
            if pattern.match(command):
                return True

        return False

    @staticmethod
    def _extract_paths_from_command(command: str) -> list[str]:
        """Extract file paths from a command using structured parsing.

        Uses shlex to properly parse the command, then identifies
        arguments that look like file paths for dangerous commands.

        Returns:
            List of file paths found in the command.
        """
        try:
            tokens = shlex.split(command)
        except ValueError:
            # Malformed command (unmatched quotes, etc.)
            return []

        paths: list[str] = []
        # Commands that take file path arguments in dangerous ways
        path_commands = {
            "rm": {"-r", "-rf", "-fr", "--recursive"},
            "mv": set(),
            "cp": set(),
            "chmod": set(),
            "chown": set(),
            "ln": {"-s", "-sf", "--symbolic"},
        }

        if not tokens:
            return paths

        base_cmd = tokens[0].split("/")[-1]  # Handle /usr/bin/rm -> rm

        if base_cmd not in path_commands:
            return paths

        # Collect non-flag arguments as potential paths
        for token in tokens[1:]:
            if token.startswith("-"):
                continue
            # It's a path argument
            paths.append(token)

        return paths
