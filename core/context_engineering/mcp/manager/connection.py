"""Connection management for MCP servers."""

import asyncio
import concurrent.futures
import threading
import time
from typing import Callable, Dict, List, Optional

from fastmcp import Client


class ConnectionMixin:
    """Mixin for MCP server connection lifecycle."""

    async def _connect_internal(self, server_name: str) -> bool:
        """Internal coroutine that performs MCP server connection."""
        from opendev.core.context_engineering.mcp.config import prepare_server_config
        from opendev.core.context_engineering.mcp.manager.manager import _SuppressStderr

        config = self.get_config()

        if server_name not in config.mcp_servers:
            print(f"Error: Server '{server_name}' not found in configuration")
            return False

        server_config = config.mcp_servers[server_name]

        if not server_config.enabled:
            print(f"Warning: Server '{server_name}' is disabled")
            return False

        # Clean up any stale client before reconnecting
        if server_name in self.clients:
            try:
                await self._disconnect_internal(server_name)
            except Exception:
                # Force remove stale client
                self.clients.pop(server_name, None)
                self.server_tools.pop(server_name, None)

        # Prepare config (expand env vars)
        prepared_config = prepare_server_config(server_config)
        client = None

        try:
            # Suppress stderr during connection to hide MCP server logs
            with _SuppressStderr():
                # Create transport based on config (supports stdio, http, sse)
                transport = self._create_transport_from_config(prepared_config)

                # Create FastMCP client
                client = Client(transport)
                await client.__aenter__()

            # Store client (outside stderr suppression)
            self.clients[server_name] = client

            # Discover tools
            await self._discover_tools(server_name)

            return True

        except Exception as e:
            # Log the error for debugging intermittent connection failures
            import logging

            logging.getLogger(__name__).debug(
                f"MCP connection failed for '{server_name}': {type(e).__name__}: {e}"
            )
            # Clean up partial connection
            if client is not None:
                try:
                    await client.__aexit__(None, None, None)
                except Exception:
                    pass
            self.clients.pop(server_name, None)
            self.server_tools.pop(server_name, None)
            return False

    async def _disconnect_internal(self, server_name: str) -> None:
        """Internal coroutine that disconnects an MCP server."""
        from opendev.core.context_engineering.mcp.manager.manager import _SuppressStderr

        if server_name in self.clients:
            client = self.clients[server_name]
            try:
                # Suppress stderr during disconnect to hide MCP server logs
                with _SuppressStderr():
                    await client.__aexit__(None, None, None)
            except Exception as e:
                print(f"Error disconnecting from '{server_name}': {e}")
            finally:
                del self.clients[server_name]
                if server_name in self.server_tools:
                    del self.server_tools[server_name]

    async def _disconnect_all_internal(self) -> None:
        """Internal coroutine that disconnects all MCP servers."""
        server_names = list(self.clients.keys())
        for server_name in server_names:
            await self._disconnect_internal(server_name)

    async def _discover_tools(self, server_name: str) -> None:
        """Discover tools from an MCP server.

        Args:
            server_name: Name of the server
        """
        if server_name not in self.clients:
            return

        client = self.clients[server_name]

        try:
            # List tools from the server
            tools = await client.list_tools()

            # Convert to our format
            tool_schemas = []
            for tool in tools:
                tool_schema = {
                    "name": f"mcp__{server_name}__{tool.name}",
                    "description": tool.description or f"Tool from {server_name} MCP server",
                    "input_schema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                    "mcp_server": server_name,
                    "mcp_tool_name": tool.name,
                }
                tool_schemas.append(tool_schema)

            self.server_tools[server_name] = tool_schemas

        except Exception as e:
            print(f"Error discovering tools from '{server_name}': {e}")
            self.server_tools[server_name] = []

    async def _connect_enabled_servers_internal(self) -> Dict[str, bool]:
        """Internal coroutine that connects to all enabled servers."""
        config = self.get_config()
        results = {}

        for server_name, server_config in config.mcp_servers.items():
            if server_config.enabled and server_config.auto_start:
                success = await self._connect_internal(server_name)
                results[server_name] = success

        return results

    # Synchronous wrappers that use the shared event loop

    def connect_sync(self, server_name: str, timeout: int = 60) -> bool:
        """Connect to an MCP server (synchronous wrapper).

        Args:
            server_name: Name of the server to connect to
            timeout: Connection timeout in seconds (default 60)

        Returns:
            True if connection successful, False otherwise
        """
        # Use per-server lock to prevent concurrent connection attempts
        with self._get_server_lock(server_name):
            return self._run_coroutine_threadsafe(
                self._connect_internal(server_name), timeout=timeout
            )

    def disconnect_sync(self, server_name: str) -> None:
        """Disconnect from an MCP server (synchronous wrapper).

        Args:
            server_name: Name of the server to disconnect from
        """
        # Use per-server lock to prevent concurrent disconnect attempts
        with self._get_server_lock(server_name):
            self._run_coroutine_threadsafe(self._disconnect_internal(server_name))

    def disconnect_all_sync(self) -> None:
        """Disconnect from all MCP servers (synchronous wrapper)."""
        self._run_coroutine_threadsafe(self._disconnect_all_internal())

    def connect_enabled_servers_sync(self) -> Dict[str, bool]:
        """Connect to all enabled servers (synchronous wrapper).

        Returns:
            Dict mapping server names to connection success status
        """
        return self._run_coroutine_threadsafe(self._connect_enabled_servers_internal())

    def connect_enabled_servers_background(
        self,
        on_complete: Optional[Callable[[Dict[str, bool]], None]] = None,
    ):
        """Schedule enabled server connections without blocking.

        Args:
            on_complete: Optional callback invoked with results dict when done.
                Receives `None` if the connection attempt fails.

        Returns:
            Future representing the in-flight connection task.
        """
        self._ensure_event_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._connect_enabled_servers_internal(),
            self._event_loop,
        )

        if on_complete is not None:

            def _callback(done_future):
                try:
                    result = done_future.result()
                except Exception:  # pragma: no cover - defensive
                    on_complete(None)
                else:
                    on_complete(result)

            future.add_done_callback(_callback)

        return future

    def call_tool_sync(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict,
        task_monitor=None,
    ) -> Dict:
        """Execute an MCP tool (synchronous wrapper).

        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool (without mcp__server__ prefix)
            arguments: Tool arguments
            task_monitor: Optional task monitor for interrupt checking

        Returns:
            Tool execution result
        """
        # Check interrupt before starting
        if task_monitor and task_monitor.should_interrupt():
            return {
                "success": False,
                "interrupted": True,
                "error": "Interrupted",
                "output": None,
            }

        self._ensure_event_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._call_tool_internal(server_name, tool_name, arguments),
            self._event_loop,
        )

        # Poll for interrupt while waiting for result
        poll_interval = 0.1  # 100ms polling
        timeout = 30  # 30 second overall timeout

        start_time = time.monotonic()
        while True:
            # Check for interrupt
            if task_monitor and task_monitor.should_interrupt():
                future.cancel()
                return {
                    "success": False,
                    "interrupted": True,
                    "error": "Interrupted",
                    "output": None,
                }

            # Check for timeout
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                future.cancel()
                return {
                    "success": False,
                    "error": f"MCP tool execution timed out after {timeout}s",
                    "output": None,
                }

            # Try to get result with short timeout
            try:
                return future.result(timeout=poll_interval)
            except concurrent.futures.TimeoutError:
                continue  # Continue polling
            except concurrent.futures.CancelledError:
                return {
                    "success": False,
                    "interrupted": True,
                    "error": "Cancelled",
                    "output": None,
                }

    def get_all_tools(self) -> List[Dict]:
        """Get all tools from all connected servers.

        Returns:
            List of tool schemas
        """
        all_tools = []
        for server_name, tools in self.server_tools.items():
            all_tools.extend(tools)
        return all_tools

    def get_server_tools(self, server_name: str) -> List[Dict]:
        """Get tools from a specific server.

        Args:
            server_name: Name of the server

        Returns:
            List of tool schemas for that server
        """
        return self.server_tools.get(server_name, [])

    async def _call_tool_internal(self, server_name: str, tool_name: str, arguments: Dict) -> Dict:
        """Internal coroutine that executes an MCP tool."""
        if server_name not in self.clients:
            return {
                "success": False,
                "error": f"Not connected to server '{server_name}'",
            }

        client = self.clients[server_name]

        try:
            result = await client.call_tool(tool_name, arguments, raise_on_error=False)

            # Check for tool-level error
            if result.is_error:
                error_text = ""
                if result.content:
                    error_text = (
                        result.content[0].text
                        if hasattr(result.content[0], "text")
                        else str(result.content[0])
                    )
                return {
                    "success": False,
                    "error": (
                        f"Tool returned error: {error_text}"
                        if error_text
                        else "Tool returned error"
                    ),
                    "output": error_text,
                }

            # Extract text content - prefer .content, fall back to .data
            if result.content:
                content = (
                    result.content[0].text
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            else:
                content = str(result.data) if result.data is not None else ""

            return {
                "success": True,
                "output": content,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
            }

    async def connect(self, server_name: str) -> bool:
        """Connect to an MCP server, delegating to the manager event loop if needed."""
        loop = asyncio.get_running_loop()
        if self._event_loop and loop is self._event_loop:
            return await self._connect_internal(server_name)
        if threading.current_thread() is self._loop_thread:
            return await self._connect_internal(server_name)
        return await asyncio.to_thread(self.connect_sync, server_name)

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server, delegating to the manager event loop if needed."""
        loop = asyncio.get_running_loop()
        if self._event_loop and loop is self._event_loop:
            await self._disconnect_internal(server_name)
            return
        if threading.current_thread() is self._loop_thread:
            await self._disconnect_internal(server_name)
            return
        await asyncio.to_thread(self.disconnect_sync, server_name)

    async def disconnect_all(self) -> None:
        """Disconnect all MCP servers, delegating to the manager event loop if needed."""
        loop = asyncio.get_running_loop()
        if self._event_loop and loop is self._event_loop:
            await self._disconnect_all_internal()
            return
        if threading.current_thread() is self._loop_thread:
            await self._disconnect_all_internal()
            return
        await asyncio.to_thread(self.disconnect_all_sync)

    async def connect_enabled_servers(self) -> Dict[str, bool]:
        """Connect enabled MCP servers, delegating to the manager event loop if needed."""
        loop = asyncio.get_running_loop()
        if self._event_loop and loop is self._event_loop:
            return await self._connect_enabled_servers_internal()
        if threading.current_thread() is self._loop_thread:
            return await self._connect_enabled_servers_internal()
        return await asyncio.to_thread(self.connect_enabled_servers_sync)

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict) -> Dict:
        """Execute an MCP tool, delegating to the manager event loop if needed."""
        loop = asyncio.get_running_loop()
        if self._event_loop and loop is self._event_loop:
            return await self._call_tool_internal(server_name, tool_name, arguments)
        if threading.current_thread() is self._loop_thread:
            return await self._call_tool_internal(server_name, tool_name, arguments)
        return await asyncio.to_thread(
            self.call_tool_sync,
            server_name,
            tool_name,
            arguments,
        )

    def is_connected(self, server_name: str) -> bool:
        """Check if a server is connected.

        Args:
            server_name: Name of the server

        Returns:
            True if connected, False otherwise
        """
        return server_name in self.clients
