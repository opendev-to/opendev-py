"""Main MCPManager class."""

import asyncio
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from fastmcp import Client

from opendev.core.context_engineering.mcp.config import (
    load_config,
    get_project_config_path,
    merge_configs,
)
from opendev.core.context_engineering.mcp.models import MCPConfig
from opendev.core.context_engineering.mcp.manager.transport import TransportMixin
from opendev.core.context_engineering.mcp.manager.connection import ConnectionMixin
from opendev.core.context_engineering.mcp.manager.server_config import ServerConfigMixin


class _SuppressStderr:
    """Context manager to temporarily suppress stderr output at the file descriptor level."""

    def __enter__(self):
        # Save the original stderr file descriptor
        self.old_stderr_fd = os.dup(2)
        # Open /dev/null
        self.devnull_fd = os.open(os.devnull, os.O_WRONLY)
        # Redirect stderr (fd 2) to /dev/null
        os.dup2(self.devnull_fd, 2)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore stderr
        os.dup2(self.old_stderr_fd, 2)
        # Close file descriptors
        os.close(self.old_stderr_fd)
        os.close(self.devnull_fd)
        return False


class MCPManager(TransportMixin, ConnectionMixin, ServerConfigMixin):
    """Manages MCP server connections and tool execution."""

    def __init__(self, working_dir: Optional[Path] = None):
        """Initialize MCP manager.

        Args:
            working_dir: Working directory for project-level config
        """
        self.working_dir = working_dir or Path.cwd()
        self.clients: Dict[str, "Client"] = {}  # server_name -> Client instance
        self.server_tools: Dict[str, List[Dict]] = {}  # server_name -> list of tool schemas
        self._config: Optional[MCPConfig] = None
        self._event_loop = None  # Shared event loop for all MCP operations
        self._loop_thread = None  # Background thread running the event loop
        self._loop_started = threading.Event()  # Signal when loop is ready
        self._loop_lock = threading.Lock()  # Lock for event loop initialization
        self._server_locks: Dict[str, threading.Lock] = {}  # Per-server locks
        self._server_locks_lock = threading.Lock()  # Lock for creating server locks

    # Event loop infrastructure

    def _run_event_loop(self):
        """Run event loop in background thread."""
        self._event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._event_loop)
        # Schedule signal AFTER loop starts - ensures run_forever() is active
        self._event_loop.call_soon(self._loop_started.set)
        try:
            self._event_loop.run_forever()
        finally:
            self._event_loop.close()

    def _ensure_event_loop(self):
        """Ensure background event loop is running (thread-safe)."""
        with self._loop_lock:
            if self._event_loop is None or not self._event_loop.is_running():
                # Reset the event before creating new loop
                self._loop_started = threading.Event()
                self._loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
                self._loop_thread.start()
                self._loop_started.wait()  # Wait for loop to be ready

    def _run_coroutine_threadsafe(self, coro, timeout=30):
        """Run a coroutine in the shared event loop and wait for result.

        Args:
            coro: Coroutine to run
            timeout: Timeout in seconds

        Returns:
            Result of the coroutine
        """
        self._ensure_event_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._event_loop)
        return future.result(timeout=timeout)

    def _get_server_lock(self, server_name: str) -> threading.Lock:
        """Get or create a lock for a specific server (thread-safe).

        Args:
            server_name: Name of the server

        Returns:
            Lock for the server
        """
        with self._server_locks_lock:
            if server_name not in self._server_locks:
                self._server_locks[server_name] = threading.Lock()
            return self._server_locks[server_name]

    # Configuration

    def load_configuration(self) -> MCPConfig:
        """Load MCP configuration from global and project files.

        Returns:
            Merged MCP configuration
        """
        # Load global config
        global_config = load_config()

        # Load project config if exists
        project_config_path = get_project_config_path(self.working_dir)
        project_config = load_config(project_config_path) if project_config_path else None

        # Merge configs
        self._config = merge_configs(global_config, project_config)
        return self._config

    def get_config(self) -> MCPConfig:
        """Get loaded configuration.

        Returns:
            MCP configuration
        """
        if self._config is None:
            self._config = self.load_configuration()
        return self._config

    # MCP Prompts

    async def _list_prompts_internal(self) -> List[dict]:
        """Internal coroutine to list prompts from all connected MCP servers."""
        prompts: List[dict] = []
        for server_name, client in self.clients.items():
            try:
                result = await client.list_prompts()
                for prompt in result.prompts:
                    prompts.append({
                        "server_name": server_name,
                        "prompt_name": prompt.name,
                        "description": prompt.description or "",
                        "arguments": [a.name for a in (prompt.arguments or [])],
                        "command": f"/{server_name}:{prompt.name}",
                    })
            except Exception:
                continue
        return prompts

    def list_prompts_sync(self, timeout: int = 15) -> List[dict]:
        """List available prompts from all connected MCP servers.

        Returns:
            List of dicts with server_name, prompt_name, description, arguments, command.
        """
        return self._run_coroutine_threadsafe(
            self._list_prompts_internal(), timeout=timeout
        )

    async def _get_prompt_internal(
        self, server_name: str, prompt_name: str, arguments: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """Internal coroutine to get a prompt from an MCP server."""
        if server_name not in self.clients:
            return None
        client = self.clients[server_name]
        try:
            result = await client.get_prompt(prompt_name, arguments or {})
            # Extract text from prompt messages
            parts = []
            for msg in result.messages:
                if hasattr(msg.content, "text"):
                    parts.append(msg.content.text)
                elif isinstance(msg.content, str):
                    parts.append(msg.content)
                elif isinstance(msg.content, list):
                    for block in msg.content:
                        if hasattr(block, "text"):
                            parts.append(block.text)
            return "\n".join(parts) if parts else str(result)
        except Exception as e:
            return f"Error getting prompt: {e}"

    def get_prompt_sync(
        self, server_name: str, prompt_name: str, arguments: Optional[Dict[str, str]] = None,
        timeout: int = 15,
    ) -> Optional[str]:
        """Get a prompt from an MCP server (synchronous wrapper).

        Args:
            server_name: Name of the MCP server.
            prompt_name: Name of the prompt.
            arguments: Optional arguments for the prompt.
            timeout: Timeout in seconds.

        Returns:
            The prompt text, or None if unavailable.
        """
        return self._run_coroutine_threadsafe(
            self._get_prompt_internal(server_name, prompt_name, arguments),
            timeout=timeout,
        )
