"""Session-model commands for per-session model configuration.

/session-model opens the same model picker as /models, but saves to
session metadata instead of global config. The selection only lasts
for the current session and is restored on resume.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.console import Console

from opendev.repl.commands.base import CommandHandler, CommandResult

if TYPE_CHECKING:
    from opendev.core.context_engineering.history import SessionManager
    from opendev.core.runtime import ConfigManager
    from opendev.core.runtime.session_model import SessionModelManager


class SessionModelCommands(CommandHandler):
    """Handler for /session-model command.

    Works like /models but saves to session instead of global config.
    """

    def __init__(
        self,
        console: Console,
        config_manager: "ConfigManager",
        session_manager: "SessionManager",
        session_model_manager: "SessionModelManager",
        rebuild_agents_callback=None,
        chat_app=None,
    ):
        super().__init__(console)
        self.config_manager = config_manager
        self.session_manager = session_manager
        self.session_model_manager = session_model_manager
        self.rebuild_agents_callback = rebuild_agents_callback
        self.chat_app = chat_app

    def handle(self, args: str) -> CommandResult:
        """Handle /session-model — open model picker or clear."""
        args = args.strip().lower()
        if args == "clear":
            return self.clear()
        # Default: open model picker (same as /models but session-scoped)
        return self.show_model_selector()

    def show_model_selector(self) -> CommandResult:
        """Open model picker (sync wrapper)."""
        if self.chat_app:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.show_model_selector_async())
        else:
            self.print_error("Interactive model picker not available in this mode")
            return CommandResult(success=False, message="Chat app not available")

    async def show_model_selector_async(self) -> CommandResult:
        """Open the same category→model picker as /models, saving to session."""
        if not self.chat_app:
            self.print_error("Interactive model selector not available in this mode")
            return CommandResult(success=False, message="Chat app not available")

        # Find config_commands to reuse its category selector + model picker UI
        config_commands = getattr(self.chat_app, "_config_commands", None)
        if config_commands is None:
            runner = getattr(self.chat_app, "runner", None)
            repl = getattr(runner, "repl", None) if runner else None
            config_commands = getattr(repl, "config_commands", None) if repl else None

        if not config_commands:
            self.print_error("Config commands not available")
            return CommandResult(success=False, message="Config commands unavailable")

        while True:
            selected_category = await config_commands._show_category_selector()
            if not selected_category:
                return CommandResult(success=False, message="Selection cancelled")

            if selected_category == "finish":
                self._show_summary()
                return CommandResult(success=True, message="Session model configured")

            selected, item = await self.chat_app.model_selector_modal_manager.show_model_selector(
                selection_mode=selected_category
            )

            if not selected or not item:
                return CommandResult(success=False, message="Selection cancelled")

            if item.get("type") == "back":
                continue

            provider_id = item["provider_id"]
            model_id = item["model_id"]
            mode = item.get("mode", "normal")

            result = self._apply_selection(provider_id, model_id, mode)
            if not result.success:
                return result

    def _apply_selection(self, provider_id: str, model_id: str, mode: str) -> CommandResult:
        """Apply a model selection to the session overlay."""
        from opendev.core.runtime.session_model import set_session_model

        session = self.session_manager.get_current_session()
        if not session:
            self.print_error("No active session")
            return CommandResult(success=False, message="No active session")

        overlay = self.session_model_manager.get_overlay() or {}

        mode_to_keys = {
            "normal": ("model_provider", "model"),
            "thinking": ("model_thinking_provider", "model_thinking"),
            "vlm": ("model_vlm_provider", "model_vlm"),
            "critique": ("model_critique_provider", "model_critique"),
            "compact": ("model_compact_provider", "model_compact"),
        }

        prov_key, model_key = mode_to_keys.get(mode, ("model_provider", "model"))
        overlay[prov_key] = provider_id
        overlay[model_key] = model_id

        # Restore old overlay, then apply updated one
        self.session_model_manager.restore()
        self.session_model_manager.apply(overlay)

        # Persist and rebuild
        set_session_model(session, overlay)
        self.session_manager.save_session()
        if self.rebuild_agents_callback:
            self.rebuild_agents_callback()

        return CommandResult(success=True)

    def _show_summary(self) -> None:
        """Show summary of session model config in conversation."""
        overlay = self.session_model_manager.get_overlay()
        if not overlay or not self.chat_app:
            return

        if hasattr(self.chat_app, "conversation"):
            lines = ["Session model configured:"]
            pairs = [
                ("Normal", "model_provider", "model"),
                ("Thinking", "model_thinking_provider", "model_thinking"),
                ("Vision", "model_vlm_provider", "model_vlm"),
                ("Critique", "model_critique_provider", "model_critique"),
                ("Compact", "model_compact_provider", "model_compact"),
            ]
            for label, prov_key, model_key in pairs:
                if model_key in overlay:
                    prov = overlay.get(prov_key, "?")
                    model = _short(overlay[model_key])
                    lines.append(f"  {label}: {prov}/{model} [session]")
            self.chat_app.conversation.add_system_message("\n".join(lines))
            self.chat_app._update_conversation_buffer()
            self.chat_app.app.invalidate()

    def clear(self) -> CommandResult:
        """Remove session model overlay, revert to global config."""
        from opendev.core.runtime.session_model import clear_session_model

        session = self.session_manager.get_current_session()
        if not session:
            self.print_error("No active session")
            return CommandResult(success=False, message="No active session")

        if not self.session_model_manager.is_active:
            self.print_warning("No session model is active.")
            self.print_spacing()
            return CommandResult(success=False, message="No session model active")

        self.session_model_manager.restore()
        clear_session_model(session)
        self.session_manager.save_session()

        if self.rebuild_agents_callback:
            self.rebuild_agents_callback()

        self.print_command_header("Session Model")
        self.print_success("Session model cleared. Using global config.")
        self.print_spacing()
        return CommandResult(success=True, message="Session model cleared")


def _short(model_id: str) -> str:
    """Shorten model ID to last segment."""
    if "/" in model_id:
        return model_id.split("/")[-1]
    return model_id
