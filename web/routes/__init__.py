"""API routes for web UI."""

from opendev.web.routes.chat import router as chat_router
from opendev.web.routes.sessions import router as sessions_router
from opendev.web.routes.config import router as config_router
from opendev.web.routes.commands import router as commands_router
from opendev.web.routes.mcp import router as mcp_router
from opendev.web.routes.auth import router as auth_router
from opendev.web.routes.traces import router as traces_router

__all__ = [
    "chat_router",
    "sessions_router",
    "config_router",
    "commands_router",
    "mcp_router",
    "auth_router",
    "traces_router",
]
