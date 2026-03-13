"""Agents listing tool — enumerate available subagent types."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentsTool:
    """List available subagent types with descriptions."""

    def list_agents(self, subagent_manager: Any = None) -> dict[str, Any]:
        """List available subagent types.

        Args:
            subagent_manager: SubAgentManager instance

        Returns:
            Result dict with agent type list
        """
        if not subagent_manager:
            return {
                "success": True,
                "output": "No subagent manager configured.",
                "agents": [],
            }

        try:
            agents = []
            # Try to get registered agent types
            if hasattr(subagent_manager, 'get_available_agents'):
                agent_types = subagent_manager.get_available_agents()
                for agent_type in agent_types:
                    agents.append({
                        "name": agent_type.get("name", "unknown"),
                        "description": agent_type.get("description", ""),
                        "tools": agent_type.get("allowed_tools", []),
                    })
            elif hasattr(subagent_manager, '_agent_configs'):
                # Fallback: read from internal configs
                for name, config in subagent_manager._agent_configs.items():
                    agents.append({
                        "name": name,
                        "description": getattr(config, 'description', str(config)),
                        "tools": getattr(config, 'allowed_tools', []),
                    })
            else:
                # Last resort: try to discover from subagent directory
                from pathlib import Path
                subagent_dir = (
                    Path(__file__).parent.parent.parent / "agents" / "subagents" / "agents"
                )
                if subagent_dir.exists():
                    for agent_dir in sorted(subagent_dir.iterdir()):
                        if agent_dir.is_dir() and not agent_dir.name.startswith("_"):
                            agents.append({
                                "name": agent_dir.name,
                                "description": f"Subagent type: {agent_dir.name}",
                                "tools": [],
                            })

            if not agents:
                return {
                    "success": True,
                    "output": "No subagent types found.",
                    "agents": [],
                }

            parts = [f"Available agents ({len(agents)}):\n"]
            for a in agents:
                parts.append(f"  {a['name']}: {a['description']}")
                if a['tools']:
                    parts.append(f"    Tools: {', '.join(a['tools'][:10])}")

            return {
                "success": True,
                "output": "\n".join(parts),
                "agents": agents,
            }
        except Exception as e:
            logger.error("Failed to list agents: %s", e, exc_info=True)
            return {"success": False, "error": f"Failed to list agents: {e}", "output": None}
