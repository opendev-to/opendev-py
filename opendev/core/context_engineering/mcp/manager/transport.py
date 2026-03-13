"""Transport creation for MCP server connections."""

from typing import Dict, List, Optional

from fastmcp.client.transports import (
    NpxStdioTransport,
    NodeStdioTransport,
    PythonStdioTransport,
    UvxStdioTransport,
    StdioTransport,
    StreamableHttpTransport,
    SSETransport,
)

from opendev.core.context_engineering.mcp.models import MCPServerConfig


class TransportMixin:
    """Mixin for creating MCP transports."""

    def _create_transport_from_config(self, server_config: MCPServerConfig):
        """Create appropriate transport based on server configuration.

        Args:
            server_config: Server configuration with transport type, url, headers, command, args, env

        Returns:
            Transport object for fastmcp Client
        """
        transport_type = server_config.transport.lower()

        # HTTP transport for remote servers
        if transport_type == "http":
            if not server_config.url:
                raise ValueError("HTTP transport requires a URL")
            return StreamableHttpTransport(
                url=server_config.url,
                headers=server_config.headers or None,
            )

        # SSE transport for server-sent events
        elif transport_type == "sse":
            if not server_config.url:
                raise ValueError("SSE transport requires a URL")
            return SSETransport(
                url=server_config.url,
                headers=server_config.headers or None,
            )

        # Stdio transport (default)
        else:
            return self._create_stdio_transport(
                server_config.command,
                server_config.args,
                server_config.env,
            )

    def _create_stdio_transport(
        self, command: str, args: List[str], env: Optional[Dict[str, str]]
    ):
        """Create appropriate stdio transport based on command type.

        Args:
            command: Command to run (npx, node, python, uv, uvx, etc.)
            args: Command arguments
            env: Environment variables

        Returns:
            Transport object for fastmcp Client
        """
        # Map command types to transport classes
        if command == "npx":
            # For npx, first arg should be package name
            if args:
                package = args[0]
                remaining_args = args[1:]
                return NpxStdioTransport(package=package, args=remaining_args)
            else:
                raise ValueError("npx command requires at least one argument (package name)")

        elif command == "node":
            # For node, first arg should be script path
            if args:
                script = args[0]
                remaining_args = args[1:]
                return NodeStdioTransport(script_path=script, args=remaining_args)
            else:
                raise ValueError("node command requires at least one argument (script path)")

        elif command in ["python", "python3"]:
            # For python, first arg should be script path
            if args:
                script = args[0]
                remaining_args = args[1:]
                return PythonStdioTransport(script_path=script, args=remaining_args)
            else:
                raise ValueError("python command requires at least one argument (script path)")

        elif command == "uv":
            # Use generic StdioTransport for uv since our config format
            # stores full args (e.g., ["run", "mcp-server-X", ...]) which
            # conflicts with UvStdioTransport's own "uv run" prefix.
            if not args:
                raise ValueError("uv command requires arguments")
            return StdioTransport(command="uv", args=args, env=env)

        elif command == "uvx":
            # For uvx, first arg should be package name
            if args:
                package = args[0]
                remaining_args = args[1:]
                # UvxStdioTransport might not support env
                return UvxStdioTransport(tool_name=package, tool_args=remaining_args)
            else:
                raise ValueError("uvx command requires at least one argument (package name)")

        elif command == "docker":
            # Docker runs as a generic command with all args
            return StdioTransport(command=command, args=args, env=env)

        else:
            # Generic stdio transport for other commands - this one supports env
            return StdioTransport(command=command, args=args, env=env)
