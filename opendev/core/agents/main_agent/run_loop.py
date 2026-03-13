"""ReAct run loop and message injection."""

import json
import logging
import queue as queue_mod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from opendev.core.agents.prompts import get_reminder
from opendev.core.utils.sound import play_finish_sound

PARALLELIZABLE_TOOLS = frozenset(
    {
        "read_file",
        "list_files",
        "search",
        "fetch_url",
        "web_search",
        "capture_web_screenshot",
        "analyze_image",
        "list_processes",
        "get_process_output",
        "list_todos",
        "search_tools",
        "find_symbol",
        "find_referencing_symbols",
    }
)


class RunLoopMixin:
    """Mixin for the main agent run loop."""

    _result_sanitizer = None  # Lazy init

    def inject_user_message(self, text: str) -> None:
        """Inject a user message into the running agent loop.

        Thread-safe. Called from the WebSocket handler thread.
        Messages exceeding the queue capacity (10) are logged and dropped.
        """
        _logger = logging.getLogger(__name__)
        try:
            self._injection_queue.put_nowait(text)
        except queue_mod.Full:
            _logger.warning("Injection queue full, dropping message: %s", text[:80])

    def _drain_injected_messages(self, messages: list, max_per_drain: int = 3) -> int:
        """Drain injected user messages into the conversation.

        Appends each message to *messages* and persists to the session if a
        session manager is available (set during run_sync). The WebSocket
        handler does NOT persist -- all writes happen on the agent thread (EC5).

        Returns:
            Number of messages drained.
        """
        _logger = logging.getLogger(__name__)
        from opendev.models.message import ChatMessage, Role

        session_mgr = getattr(self, "_run_session_manager", None)
        count = 0
        while count < max_per_drain:
            try:
                text = self._injection_queue.get_nowait()
            except queue_mod.Empty:
                break
            messages.append({"role": "user", "content": text})
            if session_mgr is not None:
                user_msg = ChatMessage(role=Role.USER, content=text)
                session_mgr.add_message(user_msg)
            count += 1
            _logger.info("Drained injected message (%d): %s", count, text[:60])
        return count

    def _reset_stuck_todos(self, interrupted: bool) -> None:
        """Reset any todos stuck in 'doing' status back to 'todo'.

        Called in the finally block of run_sync to ensure no todos remain
        spinning after the agent loop exits (due to interrupt, error, timeout,
        or internet loss).
        """
        _logger = logging.getLogger(__name__)
        todo_handler = getattr(getattr(self, "tool_registry", None), "todo_handler", None)
        if todo_handler is None:
            return
        for todo in list(todo_handler._todos.values()):
            if todo.status == "doing":
                todo.status = "todo"
                _logger.debug("[TODO] Reset stuck 'doing' todo back to 'todo': %s", todo.id)

    def _final_drain_injection_queue(self) -> None:
        """Persist any late-arriving injected messages before exiting run_sync (EC1)."""
        from opendev.models.message import ChatMessage, Role

        session_mgr = getattr(self, "_run_session_manager", None)
        while True:
            try:
                text = self._injection_queue.get_nowait()
                if session_mgr is not None:
                    user_msg = ChatMessage(role=Role.USER, content=text)
                    session_mgr.add_message(user_msg)
            except queue_mod.Empty:
                break
        self._run_session_manager = None

    @staticmethod
    def _format_tool_result(tool_name: str, result: dict) -> str:
        """Format a tool execution result into a string for the message history."""
        # Apply sanitization to prevent context bloat
        from opendev.core.context_engineering.tools.result_sanitizer import ToolResultSanitizer

        if RunLoopMixin._result_sanitizer is None:
            RunLoopMixin._result_sanitizer = ToolResultSanitizer()
        result = RunLoopMixin._result_sanitizer.sanitize(tool_name, result)

        separate_response = result.get("separate_response")
        if result["success"]:
            tool_result = separate_response if separate_response else result.get("output", "")
            completion_status = result.get("completion_status")
            if completion_status:
                tool_result = f"[completion_status={completion_status}]\n{tool_result}"
        else:
            tool_result = (
                f"Error in {tool_name}: " f"{result.get('error', 'Tool execution failed')}"
            )
        if result.get("_llm_suffix"):
            tool_result += result["_llm_suffix"]
        return tool_result

    def _execute_tools_parallel(
        self,
        tool_calls: list,
        deps: Any,
        task_monitor: Any,
        ui_callback: Any,
        is_subagent: bool,
    ) -> dict[str, dict]:
        """Execute read-only tools in parallel using a thread pool.

        Returns:
            Dict mapping tool_call_id to result dict.
        """
        _logger = logging.getLogger(__name__)
        results_by_id: dict[str, dict] = {}

        # Check interrupt before launching
        if task_monitor is not None and task_monitor.should_interrupt():
            for tc in tool_calls:
                results_by_id[tc["id"]] = {
                    "success": False,
                    "error": "Interrupted by user",
                    "output": None,
                    "interrupted": True,
                }
            return results_by_id

        # Fire on_tool_call for ALL tools upfront (before any execution starts)
        # This lets the UI show all tools simultaneously with spinners
        if ui_callback and hasattr(ui_callback, "on_tool_call"):
            for tc in tool_calls:
                t_name = tc["function"]["name"]
                t_args = json.loads(tc["function"]["arguments"])
                ui_callback.on_tool_call(t_name, t_args, tool_call_id=tc["id"])

        def _run_one(tc: dict) -> tuple[str, dict]:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
                _logger.info(f"MainAgent parallel executing tool: {name}")
                result = self.tool_registry.execute_tool(
                    name,
                    args,
                    mode_manager=deps.mode_manager,
                    approval_manager=deps.approval_manager,
                    undo_manager=deps.undo_manager,
                    session_manager=deps.session_manager,
                    task_monitor=task_monitor,
                    is_subagent=is_subagent,
                    ui_callback=ui_callback,
                )
            except Exception as e:
                result = {"success": False, "error": str(e)}
            return tc["id"], result

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_tc = {executor.submit(_run_one, tc): tc for tc in tool_calls}
            for future in as_completed(future_to_tc):
                tc = future_to_tc[future]
                try:
                    call_id, result = future.result()
                except Exception as e:
                    call_id = tc["id"]
                    result = {"success": False, "error": str(e)}
                results_by_id[call_id] = result

                # Fire on_tool_result as each tool completes (real-time)
                if ui_callback and hasattr(ui_callback, "on_tool_result"):
                    t_name = tc["function"]["name"]
                    t_args = json.loads(tc["function"]["arguments"])
                    ui_callback.on_tool_result(t_name, t_args, result, tool_call_id=tc["id"])

        return results_by_id

    def run_sync(
        self,
        message: str,
        deps: Any,
        message_history: Optional[list[dict]] = None,
        ui_callback: Optional[Any] = None,
        max_iterations: Optional[int] = None,  # None = unlimited
        task_monitor: Optional[Any] = None,  # Task monitor for interrupt support
        continue_after_subagent: bool = False,  # If True, don't inject stop after subagent
    ) -> dict:
        from opendev.core.agents.main_agent.agent import WebInterruptMonitor
        from opendev.core.context_engineering.validated_message_list import ValidatedMessageList

        messages = message_history or []
        if not isinstance(messages, ValidatedMessageList):
            messages = ValidatedMessageList(messages)

        if not messages or messages[0].get("role") != "system":
            # Use stable part as system content; dynamic part goes via _system_dynamic
            system_content = getattr(self, "_system_stable", None) or self.system_prompt
            messages.insert(0, {"role": "system", "content": system_content})

        messages.append({"role": "user", "content": message})

        # Store session manager for drain persistence (EC5)
        self._run_session_manager = getattr(deps, "session_manager", None)

        # Clear stale injected messages from any previous execution (EC2)
        while not self._injection_queue.empty():
            try:
                self._injection_queue.get_nowait()
            except queue_mod.Empty:
                break

        iteration = 0
        consecutive_no_tool_calls = 0
        MAX_NUDGE_ATTEMPTS = 3  # After this many nudges, treat as implicit completion
        todo_nudge_count = 0
        MAX_TODO_NUDGES = 4  # After this many todo nudges, allow completion anyway
        completion_nudge_sent = False
        interrupted = False
        has_explored = False  # Track whether Code-Explorer has been spawned

        try:
            while True:
                # Drain any injected user messages before this iteration
                self._drain_injected_messages(messages)

                iteration += 1

                # Safety limit only if explicitly set
                if max_iterations is not None and iteration > max_iterations:
                    return {
                        "content": "Max iterations reached without completion",
                        "messages": messages,
                        "success": False,
                    }

                # Check for interrupt request via task_monitor (Textual UI)
                if task_monitor is not None and task_monitor.should_interrupt():
                    interrupted = True
                    return {
                        "content": "Task interrupted by user",
                        "messages": messages,
                        "success": False,
                        "interrupted": True,
                    }

                # Check for interrupt request (for web UI)
                if hasattr(self, "web_state") and self.web_state.is_interrupt_requested():
                    self.web_state.clear_interrupt()
                    interrupted = True
                    return {
                        "content": "Task interrupted by user",
                        "messages": messages,
                        "success": False,
                        "interrupted": True,
                    }

                # Auto-compact context if approaching the model's token limit
                messages = self._maybe_compact(messages)

                # Route to VLM model when images are present
                model_id, http_client = self._resolve_vlm_model_and_client(messages)

                payload = {
                    "model": model_id,
                    "messages": messages,
                    "tools": self.tool_schemas,
                    "tool_choice": "auto",
                    **http_client.build_temperature_param(model_id, self.config.temperature),
                    **http_client.build_max_tokens_param(model_id, self.config.max_tokens),
                }

                # Pass dynamic system content for prompt caching (Anthropic)
                system_dynamic = getattr(self, "_system_dynamic", "")
                if system_dynamic:
                    payload["_system_dynamic"] = system_dynamic

                # Use provided task_monitor, or create WebInterruptMonitor for web UI
                monitor = task_monitor
                if monitor is None and hasattr(self, "web_state"):
                    monitor = WebInterruptMonitor(self.web_state)

                # Retry transient API errors (rate limits, server errors)
                MAX_API_RETRIES = 3
                api_retry_delays = [2, 5, 10]
                result = None
                last_api_error = ""
                for api_attempt in range(MAX_API_RETRIES):
                    result = http_client.post_json(payload, task_monitor=monitor)
                    if not result.success or result.response is None:
                        last_api_error = result.error or "Unknown error"
                        if api_attempt < MAX_API_RETRIES - 1:
                            import time as _time_mod

                            deadline = _time_mod.monotonic() + api_retry_delays[api_attempt]
                            while _time_mod.monotonic() < deadline:
                                if monitor is not None and monitor.should_interrupt():
                                    interrupted = True
                                    return {
                                        "content": "Task interrupted by user",
                                        "messages": messages,
                                        "success": False,
                                        "interrupted": True,
                                    }
                                _time_mod.sleep(0.1)
                            continue
                        return {
                            "content": last_api_error,
                            "messages": messages,
                            "success": False,
                        }

                    response = result.response
                    if response.status_code == 200:
                        break  # Success
                    elif response.status_code in (429, 500, 502, 503, 504):
                        last_api_error = f"API Error {response.status_code}: {response.text}"
                        if api_attempt < MAX_API_RETRIES - 1:
                            import time as _time_mod

                            deadline = _time_mod.monotonic() + api_retry_delays[api_attempt]
                            while _time_mod.monotonic() < deadline:
                                if monitor is not None and monitor.should_interrupt():
                                    interrupted = True
                                    return {
                                        "content": "Task interrupted by user",
                                        "messages": messages,
                                        "success": False,
                                        "interrupted": True,
                                    }
                                _time_mod.sleep(0.1)
                            continue
                        return {
                            "content": last_api_error,
                            "messages": messages,
                            "success": False,
                        }
                    else:
                        # Non-retryable error
                        return {
                            "content": f"API Error {response.status_code}: {response.text}",
                            "messages": messages,
                            "success": False,
                        }

                response_data = response.json()
                choice = response_data["choices"][0]
                message_data = choice["message"]

                # Cost tracking: record usage from this API call
                api_usage = response_data.get("usage")
                if api_usage and hasattr(self, "_cost_tracker") and self._cost_tracker:
                    model_info = self.config.get_model_info()
                    self._cost_tracker.record_usage(api_usage, model_info)
                    if ui_callback and hasattr(ui_callback, "on_cost_update"):
                        ui_callback.on_cost_update(self._cost_tracker.total_cost_usd)

                raw_content = message_data.get("content")
                cleaned_content = self._response_cleaner.clean(raw_content) if raw_content else None

                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": raw_content or "",
                }
                if "tool_calls" in message_data and message_data["tool_calls"]:
                    assistant_msg["tool_calls"] = message_data["tool_calls"]
                messages.append(assistant_msg)

                if "tool_calls" not in message_data or not message_data["tool_calls"]:
                    # No tool calls - check if we should nudge or accept implicit completion
                    # Check if last tool execution failed (should nudge to retry)
                    last_tool_failed = False
                    last_error_text = ""
                    for msg in reversed(messages):
                        if msg.get("role") == "tool":
                            content = msg.get("content", "")
                            if content.startswith("Error"):
                                last_tool_failed = True
                                last_error_text = content
                            break

                    if last_tool_failed:
                        # Last tool failed - nudge agent to fix and retry
                        consecutive_no_tool_calls += 1

                        if consecutive_no_tool_calls >= MAX_NUDGE_ATTEMPTS:
                            # Exhausted nudge attempts - check todos before accepting
                            can_complete, nudge_msg = self._check_todo_completion()
                            if not can_complete and todo_nudge_count < MAX_TODO_NUDGES:
                                todo_nudge_count += 1
                                messages.append({"role": "user", "content": nudge_msg})
                                continue

                            # Check injection queue before accepting completion
                            if not self._injection_queue.empty():
                                self._drain_injected_messages(messages)
                                consecutive_no_tool_calls = 0
                                continue

                            # Before accepting implicit completion, remind of original task (once)
                            if not completion_nudge_sent:
                                completion_nudge_sent = True
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": get_reminder(
                                            "implicit_completion_nudge",
                                            original_task=message,
                                        ),
                                    }
                                )
                                continue

                            # Accept best-effort completion
                            return {
                                "content": cleaned_content or "Done.",
                                "messages": messages,
                                "success": True,
                            }

                        # Use smart nudge with error-specific guidance
                        messages.append(
                            {
                                "role": "user",
                                "content": self._get_smart_nudge(last_error_text),
                            }
                        )
                        continue

                    # Last tool succeeded (or no previous tool) - check todos
                    can_complete, nudge_msg = self._check_todo_completion()
                    if not can_complete and todo_nudge_count < MAX_TODO_NUDGES:
                        todo_nudge_count += 1
                        messages.append({"role": "user", "content": nudge_msg})
                        continue

                    # Check injection queue before accepting implicit completion
                    if not self._injection_queue.empty():
                        self._drain_injected_messages(messages)
                        continue

                    # Before accepting implicit completion, remind of original task (once)
                    if not completion_nudge_sent:
                        completion_nudge_sent = True
                        messages.append(
                            {
                                "role": "user",
                                "content": get_reminder(
                                    "implicit_completion_nudge",
                                    original_task=message,
                                ),
                            }
                        )
                        continue

                    # Return the natural completion content directly without extra LLM calls
                    return {
                        "content": cleaned_content or "Done.",
                        "messages": messages,
                        "success": True,
                    }

                # Reset counter when we have tool calls
                consecutive_no_tool_calls = 0

                tool_calls = message_data["tool_calls"]

                # Check if this is a subagent (has overridden system prompt)
                is_subagent = (
                    hasattr(self, "_subagent_system_prompt")
                    and self._subagent_system_prompt is not None
                )

                # Detect if all tools are parallelizable (no task_complete, >1 call)
                has_task_complete = any(
                    tc["function"]["name"] == "task_complete" for tc in tool_calls
                )
                all_parallelizable = (
                    len(tool_calls) > 1
                    and not has_task_complete
                    and all(tc["function"]["name"] in PARALLELIZABLE_TOOLS for tc in tool_calls)
                )

                if all_parallelizable:
                    # Parallel path for read-only tools
                    # UI callbacks fire in real-time inside _execute_tools_parallel
                    results_by_id = self._execute_tools_parallel(
                        tool_calls, deps, task_monitor, ui_callback, is_subagent
                    )

                    # Append results to messages in original order
                    for tc in tool_calls:
                        result = results_by_id[tc["id"]]
                        t_name = tc["function"]["name"]

                        if result.get("interrupted"):
                            interrupted = True
                            return {
                                "content": "Task interrupted by user",
                                "messages": messages,
                                "success": False,
                                "interrupted": True,
                            }

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": self._format_tool_result(t_name, result),
                            }
                        )
                    continue  # Next iteration of outer while loop

                # Sequential path (original logic)
                # Explore-first enforcement: block task subagent spawns until
                # Code-Explorer has run
                _EXPLORE_EXEMPT = {"Code-Explorer", "ask-user"}
                _explore_blocked = False
                if not has_explored:
                    for tc in tool_calls:
                        if tc["function"]["name"] == "spawn_subagent":
                            tc_args = json.loads(tc["function"]["arguments"])
                            subagent_type = tc_args.get("subagent_type", "")
                            if subagent_type not in _EXPLORE_EXEMPT:
                                _explore_blocked = True
                                for t in tool_calls:
                                    if t["id"] == tc["id"]:
                                        messages.append(
                                            {
                                                "role": "tool",
                                                "tool_call_id": t["id"],
                                                "content": get_reminder("explore_first_nudge"),
                                            }
                                        )
                                    else:
                                        messages.append(
                                            {
                                                "role": "tool",
                                                "tool_call_id": t["id"],
                                                "content": "Blocked: explore first.",
                                            }
                                        )
                                break
                if _explore_blocked:
                    continue  # Next iteration of outer while loop

                # Mark explored when Code-Explorer is being spawned
                for tc in tool_calls:
                    if tc["function"]["name"] == "spawn_subagent":
                        tc_args = json.loads(tc["function"]["arguments"])
                        if tc_args.get("subagent_type", "") == "Code-Explorer":
                            has_explored = True
                            break

                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args = json.loads(tool_call["function"]["arguments"])

                    # Check for explicit task completion
                    if tool_name == "task_complete":
                        summary = tool_args.get("summary", "Task completed")
                        status = tool_args.get("status", "success")

                        # Only check todos for successful completions
                        if status == "success":
                            can_complete, nudge_msg = self._check_todo_completion()
                            if not can_complete and todo_nudge_count < MAX_TODO_NUDGES:
                                todo_nudge_count += 1
                                messages.append({"role": "user", "content": nudge_msg})
                                continue  # Reject task_complete, loop again

                        # Check injection queue before accepting task_complete
                        if not self._injection_queue.empty():
                            self._drain_injected_messages(messages)
                            # Add tool result so conversation stays valid, then continue
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call["id"],
                                    "content": ("Completion deferred: new user messages arrived."),
                                }
                            )
                            break  # Break inner for-loop, continue outer while-loop

                        return {
                            "content": summary,
                            "messages": messages,
                            "success": status != "failed",
                            "completion_status": status,
                        }

                    # Notify UI callback before tool execution
                    if ui_callback and hasattr(ui_callback, "on_tool_call"):
                        ui_callback.on_tool_call(tool_name, tool_args, tool_call_id=tool_call["id"])

                    # Log tool registry type for debugging Docker execution
                    _logger = logging.getLogger(__name__)
                    _logger.info(f"MainAgent executing tool: {tool_name}")
                    _logger.info(f"  tool_registry type: {type(self.tool_registry).__name__}")

                    result = self.tool_registry.execute_tool(
                        tool_name,
                        tool_args,
                        mode_manager=deps.mode_manager,
                        approval_manager=deps.approval_manager,
                        undo_manager=deps.undo_manager,
                        session_manager=deps.session_manager,
                        task_monitor=task_monitor,
                        is_subagent=is_subagent,
                        ui_callback=ui_callback,
                    )

                    # Notify UI callback after tool execution
                    if ui_callback and hasattr(ui_callback, "on_tool_result"):
                        ui_callback.on_tool_result(
                            tool_name, tool_args, result, tool_call_id=tool_call["id"]
                        )

                    # Check if tool execution was interrupted
                    if result.get("interrupted"):
                        interrupted = True
                        return {
                            "content": "Task interrupted by user",
                            "messages": messages,
                            "success": False,
                            "interrupted": True,
                        }

                    tool_result = self._format_tool_result(tool_name, result)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": tool_result,
                        }
                    )
        finally:
            self._final_drain_injection_queue()
            # Reset any "doing" todos back to "todo" when the run ends abnormally
            # (interrupt, error, internet drop, timeout). This prevents stuck spinners
            # in the todo panel when the agent loop exits unexpectedly.
            self._reset_stuck_todos(interrupted)
            if (
                getattr(self.config, "enable_sound", False)
                and not getattr(self, "is_subagent", False)
                and not interrupted
            ):
                play_finish_sound()
