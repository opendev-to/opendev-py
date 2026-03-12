"""Project Init subagent for OPENDEV.md generation."""

from opendev.core.agents.prompts.loader import load_prompt
from opendev.core.agents.subagents.specs import SubAgentSpec

PROJECT_INIT_SUBAGENT = SubAgentSpec(
    name="Project-Init",
    description=(
        "Analyzes a codebase and generates an OPENDEV.md project instruction file. "
        "Discovers build/test/lint commands, tech stack, and architecture. "
        "USE FOR: Setting up new projects, generating project docs. "
        "NOT FOR: General codebase exploration (use Code-Explorer instead)."
    ),
    system_prompt=load_prompt("subagents/subagent-project-init"),
    tools=["read_file", "search", "list_files", "run_command", "write_file"],
)
