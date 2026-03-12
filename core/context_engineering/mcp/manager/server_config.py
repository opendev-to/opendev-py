"""Server configuration management (add/remove/enable/disable)."""

from typing import Dict, List, Optional

from opendev.core.context_engineering.mcp.config import save_config
from opendev.core.context_engineering.mcp.models import MCPServerConfig


class ServerConfigMixin:
    """Mixin for MCP server configuration CRUD."""

    def add_server(
        self,
        name: str,
        command: str = "",
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        transport: str = "stdio",
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Add a new MCP server to configuration.

        Args:
            name: Server name
            command: Command to start the server (for stdio transport)
            args: Command arguments (for stdio transport)
            env: Environment variables (for stdio transport)
            transport: Transport type (stdio, http, sse)
            url: URL for HTTP/SSE transport
            headers: HTTP headers for HTTP/SSE transport
        """
        config = self.get_config()

        server_config = MCPServerConfig(
            command=command,
            args=args or [],
            env=env or {},
            transport=transport,
            url=url,
            headers=headers or {},
            enabled=True,
            auto_start=True,
        )

        config.mcp_servers[name] = server_config
        save_config(config)

        # Reload config
        self._config = None

    def remove_server(self, name: str) -> bool:
        """Remove an MCP server from configuration.

        Args:
            name: Server name

        Returns:
            True if server was removed, False if not found
        """
        config = self.get_config()

        if name not in config.mcp_servers:
            return False

        del config.mcp_servers[name]
        save_config(config)

        # Reload config
        self._config = None

        return True

    def enable_server(self, name: str) -> bool:
        """Enable an MCP server.

        Args:
            name: Server name

        Returns:
            True if server was enabled, False if not found
        """
        config = self.get_config()

        if name not in config.mcp_servers:
            return False

        config.mcp_servers[name].enabled = True
        save_config(config)

        # Reload config
        self._config = None

        return True

    def disable_server(self, name: str) -> bool:
        """Disable an MCP server.

        Args:
            name: Server name

        Returns:
            True if server was disabled, False if not found
        """
        config = self.get_config()

        if name not in config.mcp_servers:
            return False

        config.mcp_servers[name].enabled = False
        save_config(config)

        # Reload config
        self._config = None

        return True

    def list_servers(self) -> Dict[str, MCPServerConfig]:
        """List all configured MCP servers.

        Returns:
            Dict mapping server names to their configurations
        """
        config = self.get_config()
        return dict(config.mcp_servers)
