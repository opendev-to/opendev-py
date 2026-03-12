"""Non-interactive mode handler for OpenDev CLI."""

import sys

from rich.console import Console

from opendev.ui_textual.style_tokens import ERROR, WARNING
from opendev.core.runtime.approval import ApprovalManager
from opendev.core.runtime import ConfigManager, ModeManager
from opendev.core.context_engineering.history import SessionManager, UndoManager
from opendev.core.runtime.services import RuntimeService
from opendev.models.agent_deps import AgentDependencies
from opendev.models.message import ChatMessage, Role
from opendev.core.context_engineering.tools.implementations import (
    BashTool,
    EditTool,
    FileOperations,
    VLMTool,
    WebFetchTool,
    WebScreenshotTool,
    WriteTool,
)
from opendev.core.context_engineering.tools.implementations.web_search_tool import WebSearchTool
from opendev.core.context_engineering.tools.implementations.notebook_edit_tool import (
    NotebookEditTool,
)
from opendev.core.context_engineering.tools.implementations.ask_user_tool import AskUserTool


def _run_non_interactive(
    config_manager: ConfigManager,
    session_manager: SessionManager,
    prompt: str,
    dangerously_skip_permissions: bool = False,
) -> None:
    """Run a single prompt in non-interactive mode.

    Args:
        config_manager: Configuration manager
        session_manager: Session manager
        prompt: User prompt to execute
        dangerously_skip_permissions: If True, auto-approve all operations
    """
    console = Console()

    if dangerously_skip_permissions:
        console.print(
            f"[{WARNING}]Warning: --dangerously-skip-permissions is enabled. "
            f"All operations will be auto-approved without confirmation.[/{WARNING}]"
        )

    config = config_manager.get_config()
    mode_manager = ModeManager()
    approval_manager = ApprovalManager(console)
    if dangerously_skip_permissions:
        approval_manager.auto_approve_remaining = True
    undo_manager = UndoManager(config.max_undo_history)

    # Initialize plan file path for plan mode
    session = session_manager.get_current_session()
    if session:
        from opendev.core.paths import get_paths

        plans_dir = get_paths().global_dir / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        plan_file_path = plans_dir / f"{session.id}.md"
        mode_manager.set_plan_file_path(str(plan_file_path))

    file_ops = FileOperations(config, config_manager.working_dir)
    write_tool = WriteTool(config, config_manager.working_dir)
    edit_tool = EditTool(config, config_manager.working_dir)
    bash_tool = BashTool(config, config_manager.working_dir)
    web_fetch_tool = WebFetchTool(config, config_manager.working_dir)
    web_search_tool = WebSearchTool(config, config_manager.working_dir)
    notebook_edit_tool = NotebookEditTool(config_manager.working_dir)
    ask_user_tool = AskUserTool()  # Uses console fallback in non-interactive mode
    vlm_tool = VLMTool(config, config_manager.working_dir)
    web_screenshot_tool = WebScreenshotTool(config, config_manager.working_dir)

    runtime_service = RuntimeService(config_manager, mode_manager)
    runtime_suite = runtime_service.build_suite(
        file_ops=file_ops,
        write_tool=write_tool,
        edit_tool=edit_tool,
        bash_tool=bash_tool,
        web_fetch_tool=web_fetch_tool,
        web_search_tool=web_search_tool,
        notebook_edit_tool=notebook_edit_tool,
        ask_user_tool=ask_user_tool,
        vlm_tool=vlm_tool,
        web_screenshot_tool=web_screenshot_tool,
        mcp_manager=None,
    )

    agent = runtime_suite.agents.normal

    session = session_manager.get_current_session()
    if not session:
        session = session_manager.create_session(working_directory=str(config_manager.working_dir))

    message_history = session.to_api_messages()

    deps = AgentDependencies(
        mode_manager=mode_manager,
        approval_manager=approval_manager,
        undo_manager=undo_manager,
        session_manager=session_manager,
        working_dir=config_manager.working_dir,
        console=console,
        config=config,
    )

    try:
        result = agent.run_sync(prompt, deps, message_history=message_history)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[{ERROR}]Error: {exc}[/{ERROR}]")
        sys.exit(1)

    if not result.get("success", False):
        error = result.get("error", "Unknown error")
        console.print(f"[{ERROR}]Error: {error}[/{ERROR}]")
        sys.exit(1)

    user_msg = ChatMessage(role=Role.USER, content=prompt)
    session_manager.add_message(user_msg, config.auto_save_interval)

    assistant_content = result.get("content", "") or ""
    raw_assistant_content = assistant_content
    history = result.get("messages") or []
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            raw_assistant_content = msg.get("content", raw_assistant_content)
            break

    # Extract metadata from agent response for session persistence
    thinking_trace = result.get("thinking_trace")
    reasoning_content = result.get("reasoning_content")
    token_usage = result.get("usage")

    metadata = {}
    if raw_assistant_content is not None:
        metadata["raw_content"] = raw_assistant_content

    assistant_msg = ChatMessage(
        role=Role.ASSISTANT,
        content=assistant_content,
        metadata=metadata,
        thinking_trace=thinking_trace,
        reasoning_content=reasoning_content,
        token_usage=token_usage,
    )
    session_manager.add_message(assistant_msg, config.auto_save_interval)
    session_manager.save_session()

    console.print(assistant_content)
