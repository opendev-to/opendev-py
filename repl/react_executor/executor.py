"""ReAct loop executor."""

import hashlib
import logging
import os
import queue as queue_mod
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional, Any

from opendev.models.message import ChatMessage, Role
from opendev.core.runtime.monitoring import TaskMonitor
from opendev.core.utils.sound import play_finish_sound
from opendev.repl.react_executor.thinking import ThinkingMixin
from opendev.repl.react_executor.tool_processing import ToolProcessingMixin
from opendev.repl.react_executor.session_persistence import SessionPersistenceMixin
from opendev.repl.react_executor.iteration import IterationMixin

logger = logging.getLogger(__name__)

# Maximum number of tools to execute in parallel
MAX_CONCURRENT_TOOLS = 5

# Safety cap to prevent runaway loops
MAX_REACT_ITERATIONS = 200

_ctx_logger = logging.getLogger("swecli.context_debug")
_ctx_logger.setLevel(logging.DEBUG)
_fh = logging.FileHandler("/tmp/context_debug.log", mode="w")
_fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
_ctx_logger.addHandler(_fh)


def _debug_log(message: str) -> None:
    """Write debug message to /tmp/swecli_react_debug.log."""
    from datetime import datetime

    log_file = "/tmp/swecli_react_debug.log"
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with open(log_file, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def _session_debug() -> "SessionDebugLogger":
    """Get the current session debug logger."""
    from opendev.core.debug import get_debug_logger

    return get_debug_logger()


if TYPE_CHECKING:
    from rich.console import Console
    from opendev.core.context_engineering.history import SessionManager
    from opendev.models.config import Config
    from opendev.repl.llm_caller import LLMCaller
    from opendev.repl.tool_executor import ToolExecutor
    from opendev.core.runtime.approval import ApprovalManager
    from opendev.core.context_engineering.history import UndoManager
    from opendev.core.debug.session_debug_logger import SessionDebugLogger
    from opendev.core.runtime.cost_tracker import CostTracker


class LoopAction(Enum):
    """Action to take after an iteration."""

    CONTINUE = auto()
    BREAK = auto()


@dataclass
class IterationContext:
    """Context for a single ReAct iteration."""

    query: str
    messages: list
    agent: Any
    tool_registry: Any
    approval_manager: "ApprovalManager"
    undo_manager: "UndoManager"
    ui_callback: Optional[Any]
    iteration_count: int = 0
    consecutive_reads: int = 0
    consecutive_no_tool_calls: int = 0
    todo_nudge_count: int = 0
    plan_approved_signal_injected: bool = False
    all_todos_complete_nudged: bool = False
    completion_nudge_sent: bool = False
    skip_next_thinking: bool = False
    continue_after_subagent: bool = False  # If True, don't inject stop signal after subagent
    has_explored: bool = False  # True after Code-Explorer has been spawned
    planner_pending: bool = False  # True after Planner spawned, cleared after present_plan
    planner_plan_path: str = ""  # Plan file path from Planner spawn args
    # Doom-loop detection: track recent (tool_name, args_hash) tuples
    recent_tool_calls: deque = field(default_factory=lambda: deque(maxlen=20))
    doom_loop_nudge_count: int = 0  # How many times we've auto-nudged


class ReactExecutor(ThinkingMixin, ToolProcessingMixin, SessionPersistenceMixin, IterationMixin):
    """Executes ReAct loop (Reasoning -> Acting -> Observing)."""

    READ_OPERATIONS = {"read_file", "list_files", "search"}
    MAX_NUDGE_ATTEMPTS = 3
    MAX_TODO_NUDGES = 4  # After this many nudges, allow completion anyway
    DOOM_LOOP_THRESHOLD = 3  # Same tool+args N times -> doom loop
    MAX_CYCLE_LEN = 3  # Check for repeating cycles up to this length

    # Tools safe for silent parallel execution (read-only, no approval needed)
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

    # Threshold for offloading tool output to scratch files (chars, ~2000 tokens)
    OFFLOAD_THRESHOLD = 8000

    def __init__(
        self,
        session_manager: "SessionManager",
        config: "Config",
        mode_manager,
        console: Optional["Console"] = None,
        llm_caller: Optional["LLMCaller"] = None,
        tool_executor: Optional["ToolExecutor"] = None,
        cost_tracker: Optional["CostTracker"] = None,
        parallel_executor=None,
    ):
        """Initialize ReAct executor.

        Args:
            session_manager: Session manager for conversation persistence.
            config: Application configuration.
            mode_manager: Mode manager for plan/normal mode control.
            console: Rich console for TUI output (None for Web UI).
            llm_caller: LLM caller with progress display (None for Web UI).
            tool_executor: Tool executor for TUI (None for Web UI).
            cost_tracker: Optional cost tracker.
            parallel_executor: Optional shared ThreadPoolExecutor for parallel tools.
        """
        self.console = console
        self.session_manager = session_manager
        self.config = config
        self._mode_manager = mode_manager
        self._llm_caller = llm_caller
        self._tool_executor = tool_executor
        self._cost_tracker = cost_tracker
        self._last_operation_summary = None
        self._last_error = None
        self._last_latency_ms = 0
        self._last_thinking_error: Optional[dict[str, Any]] = None

        # Tracking variables for current iteration (for session persistence)
        self._current_thinking_trace: Optional[str] = None
        self._current_reasoning_content: Optional[str] = None
        self._current_token_usage: Optional[dict] = None

        # Track current task monitor for interrupt support (thinking phase uses this)
        self._current_task_monitor: Optional[TaskMonitor] = None

        # Centralized interrupt token for the current run
        self._active_interrupt_token: Optional[Any] = None

        # Hook manager for lifecycle hooks
        self._hook_manager = None

        # Auto-compaction support
        self._compactor = None
        self._force_compact_next = False  # Set by /compact command

        # Shadow git snapshot system for per-step undo
        self._snapshot_manager = None

        # Persistent thread pool for parallel tool execution (enables connection reuse)
        self._parallel_executor = parallel_executor or ThreadPoolExecutor(
            max_workers=MAX_CONCURRENT_TOOLS, thread_name_prefix="tool-worker"
        )

        # Live message injection queue (thread-safe, bounded)
        self._injection_queue: queue_mod.Queue[str] = queue_mod.Queue(maxsize=10)

        # Callback invoked when an injected message is consumed at a step boundary
        self._on_message_consumed: Optional[callable] = None
        # Callback for messages remaining after loop ends (need re-queuing)
        self._on_orphan_message: Optional[callable] = None

    def request_interrupt(self) -> bool:
        """Request interrupt of currently running task (thinking or tool execution).

        Returns:
            True if interrupt was requested, False if no task is running
        """
        try:
            from opendev.ui_textual.debug_logger import debug_log
        except ImportError:
            debug_log = lambda *a, **kw: None  # noqa: E731

        debug_log("ReactExecutor", "request_interrupt called")
        debug_log("ReactExecutor", f"_current_task_monitor={self._current_task_monitor}")

        if self._current_task_monitor is not None:
            self._current_task_monitor.request_interrupt()
            debug_log("ReactExecutor", "Called task_monitor.request_interrupt()")

        if self._active_interrupt_token is not None:
            self._active_interrupt_token.request()
            debug_log("ReactExecutor", "Called _active_interrupt_token.request()")
            return True

        if self._current_task_monitor is not None:
            return True
        debug_log("ReactExecutor", "No active task monitor")
        return False

    def set_hook_manager(self, hook_manager) -> None:
        """Set the hook manager for lifecycle hooks.

        Args:
            hook_manager: HookManager instance
        """
        self._hook_manager = hook_manager

    def inject_user_message(self, text: str) -> None:
        """Inject a user message into the running ReAct loop.

        Thread-safe. Called from the UI thread to deliver messages mid-execution.
        Messages exceeding the queue capacity (10) are logged and dropped.
        """
        try:
            self._injection_queue.put_nowait(text)
        except queue_mod.Full:
            logger.warning("Injection queue full, dropping message: %s", text[:80])

    def set_on_message_consumed(self, callback):
        self._on_message_consumed = callback

    def set_on_orphan_message(self, callback):
        self._on_orphan_message = callback

    def _drain_injected_messages(self, ctx: IterationContext, max_per_drain: int = 3) -> int:
        """Drain injected user messages into the conversation.

        Persists each message to the session and appends it to ctx.messages.
        Caps at *max_per_drain* messages per call; leftovers stay queued for
        the next iteration.

        Returns:
            Number of messages drained.
        """
        count = 0
        while count < max_per_drain:
            try:
                text = self._injection_queue.get_nowait()
            except queue_mod.Empty:
                break
            user_msg = ChatMessage(role=Role.USER, content=text)
            self.session_manager.add_message(user_msg, self.config.auto_save_interval)
            ctx.messages.append({"role": "user", "content": text})
            count += 1
            _debug_log(f"[INJECT] Drained injected message ({count}): {text[:60]}")
            if self._on_message_consumed is not None:
                try:
                    self._on_message_consumed(text)
                except Exception:
                    logger.debug("_on_message_consumed callback failed", exc_info=True)
        return count

    def _check_interrupt(self, phase: str = "") -> None:
        """Check interrupt token; raise InterruptedError if signaled.

        Call at every phase boundary in _run_iteration() to ensure
        prompt cancellation between thinking -> critique -> action -> tools.
        """
        if self._active_interrupt_token and self._active_interrupt_token.is_requested():
            _debug_log(f"[INTERRUPT] Token detected at phase boundary: {phase}")
            raise InterruptedError(f"Interrupted at {phase}" if phase else "Interrupted by user")

    @staticmethod
    def _tool_call_fingerprint(tool_name: str, args_str: str) -> str:
        """Compute a compact fingerprint for a tool call (name + args hash)."""
        h = hashlib.md5(args_str.encode(), usedforsecurity=False).hexdigest()[:12]
        return f"{tool_name}:{h}"

    def _detect_doom_loop(self, tool_calls: list, ctx: IterationContext) -> Optional[str]:
        """Check if the agent is stuck in a repeating cycle of tool calls.

        Detects cycles of length 1..MAX_CYCLE_LEN repeated DOOM_LOOP_THRESHOLD times.
        This avoids false positives for edit-test interleaving where the test command
        repeats but edits differ.

        Returns a warning message if a doom loop is detected, None otherwise.
        """
        for tc in tool_calls:
            fp = self._tool_call_fingerprint(tc["function"]["name"], tc["function"]["arguments"])
            ctx.recent_tool_calls.append(fp)

        tail = list(ctx.recent_tool_calls)

        for cycle_len in range(1, self.MAX_CYCLE_LEN + 1):
            required = cycle_len * self.DOOM_LOOP_THRESHOLD
            if len(tail) < required:
                continue

            # Extract the last `required` entries and check for a repeating pattern
            segment = tail[-required:]
            pattern = segment[:cycle_len]
            is_cycle = all(segment[i] == pattern[i % cycle_len] for i in range(required))

            if is_cycle:
                if cycle_len == 1:
                    tool_name = pattern[0].split(":")[0]
                    return (
                        f"The agent has called `{tool_name}` with the same arguments "
                        f"{self.DOOM_LOOP_THRESHOLD} times consecutively. "
                        f"It may be stuck in a loop."
                    )
                else:
                    tool_names = [p.split(":")[0] for p in pattern]
                    return (
                        f"The agent is repeating a {cycle_len}-step cycle "
                        f"({' -> '.join(tool_names)}) "
                        f"{self.DOOM_LOOP_THRESHOLD} times. "
                        f"It may be stuck in a loop."
                    )
        return None

    def execute(
        self,
        query: str,
        messages: list,
        agent,
        tool_registry,
        approval_manager: "ApprovalManager",
        undo_manager: "UndoManager",
        ui_callback=None,
        continue_after_subagent: bool = False,
    ) -> tuple:
        """Execute ReAct loop."""

        # Clear stale injected messages from any previous execution (EC2)
        while not self._injection_queue.empty():
            try:
                self._injection_queue.get_nowait()
            except queue_mod.Empty:
                break

        from opendev.core.runtime.interrupt_token import InterruptToken

        # Create a single interrupt token for this entire run
        self._active_interrupt_token = InterruptToken()
        self._active_interrupt_token.set_thread_ident(threading.get_ident())

        # Wire token to InterruptManager so ESC can signal it directly (Fix 1)
        _ui_callback = ui_callback  # Capture for finally block
        if _ui_callback and hasattr(_ui_callback, "chat_app"):
            app = _ui_callback.chat_app
            if app and hasattr(app, "_interrupt_manager"):
                app._interrupt_manager.set_interrupt_token(self._active_interrupt_token)

        # Wrap messages in ValidatedMessageList for write-time invariant enforcement
        from opendev.core.context_engineering.validated_message_list import ValidatedMessageList

        if not isinstance(messages, ValidatedMessageList):
            messages = ValidatedMessageList(messages)

        # Initialize context
        ctx = IterationContext(
            query=query,
            messages=messages,
            agent=agent,
            tool_registry=tool_registry,
            approval_manager=approval_manager,
            undo_manager=undo_manager,
            ui_callback=ui_callback,
            continue_after_subagent=continue_after_subagent,
        )

        # Restore cost tracker state from session metadata (for --continue)
        if self._cost_tracker:
            session = self.session_manager.get_current_session()
            if session and session.metadata.get("cost_tracking"):
                self._cost_tracker.restore_from_metadata(session.metadata)

        # Initialize snapshot manager for per-step undo
        if self._snapshot_manager is None:
            try:
                from opendev.core.context_engineering.history.snapshot import SnapshotManager

                working_dir = getattr(self.config, "working_directory", None) or os.getcwd()
                self._snapshot_manager = SnapshotManager(working_dir)
                # Capture initial state
                self._snapshot_manager.track()
            except Exception:
                logger.debug("Failed to initialize snapshot manager", exc_info=True)

        # Notify UI start
        if ui_callback and hasattr(ui_callback, "on_thinking_start"):
            ui_callback.on_thinking_start()

        # Debug: Query processing started
        if ui_callback and hasattr(ui_callback, "on_debug"):
            ui_callback.on_debug(
                f"Processing query: {query[:50]}{'...' if len(query) > 50 else ''}", "QUERY"
            )

        try:
            while True:
                # Drain any injected user messages before this iteration
                self._drain_injected_messages(ctx)

                ctx.iteration_count += 1

                # Check centralized interrupt token at each iteration boundary
                if self._active_interrupt_token and self._active_interrupt_token.is_requested():
                    _debug_log("[INTERRUPT] Token triggered, breaking loop")
                    if ctx.ui_callback and hasattr(ctx.ui_callback, "on_interrupt"):
                        ctx.ui_callback.on_interrupt()
                    break

                if ctx.iteration_count > MAX_REACT_ITERATIONS:
                    _debug_log(f"[SAFETY] Hit iteration limit ({MAX_REACT_ITERATIONS})")
                    if ctx.ui_callback and hasattr(ctx.ui_callback, "on_assistant_message"):
                        ctx.ui_callback.on_assistant_message(
                            "Reached maximum iteration limit."
                            " Please provide further instructions."
                        )
                    break

                _session_debug().log(
                    "react_iteration_start",
                    "react",
                    iteration=ctx.iteration_count,
                    query_preview=query[:200],
                    message_count=len(messages),
                )
                action = self._run_iteration(ctx)
                _session_debug().log(
                    "react_iteration_end",
                    "react",
                    iteration=ctx.iteration_count,
                    action=action.name.lower(),
                )
                if action == LoopAction.BREAK:
                    # Don't break if new messages arrived during this iteration
                    if not self._injection_queue.empty():
                        _debug_log("[INJECT] New messages in queue, continuing loop")
                        continue
                    break
        except InterruptedError:
            _debug_log("[INTERRUPT] Caught InterruptedError in execute() main loop")
        except Exception as e:
            if isinstance(e, InterruptedError):
                _debug_log("[INTERRUPT] Caught InterruptedError (via isinstance) in execute()")
            else:
                if self.console:
                    self.console.print(f"[red]Error: {str(e)}[/red]")
                import traceback

                tb = traceback.format_exc()
                traceback.print_exc()
                self._last_error = str(e)
                _session_debug().log("error", "react", error=str(e), traceback=tb)
        finally:
            interrupted = bool(
                self._active_interrupt_token and self._active_interrupt_token.is_requested()
            )

            # Fix 4: If interrupted but on_interrupt wasn't called yet, call it now
            if interrupted and _ui_callback and hasattr(_ui_callback, "on_interrupt"):
                _ui_callback.on_interrupt()

            # Fix 1: Clear token from InterruptManager
            if _ui_callback and hasattr(_ui_callback, "chat_app"):
                app = _ui_callback.chat_app
                if app and hasattr(app, "_interrupt_manager"):
                    app._interrupt_manager.clear_interrupt_token()

            self._active_interrupt_token = None

        # Final drain: re-queue or persist any late-arriving injected messages (EC1)
        while True:
            try:
                text = self._injection_queue.get_nowait()
                if self._on_orphan_message is not None:
                    self._on_orphan_message(text)
                else:
                    # Fallback: persist (preserves original behavior for non-TUI)
                    user_msg = ChatMessage(role=Role.USER, content=text)
                    self.session_manager.add_message(user_msg, self.config.auto_save_interval)
            except queue_mod.Empty:
                break

        # Clear callbacks (owned by the caller, not us)
        self._on_message_consumed = None
        self._on_orphan_message = None

        # Ensure session metadata (context_usage_pct, compaction_point, etc.)
        # is flushed to disk — auto-save may not have fired on the last turn.
        try:
            self.session_manager.save_session()
        except Exception:
            logger.debug("Final session save failed", exc_info=True)

        # Fire Stop hook (can prevent stopping by returning exit code 2)
        if self._hook_manager and not interrupted:
            from opendev.core.hooks.models import HookEvent

            if self._hook_manager.has_hooks_for(HookEvent.STOP):
                stop_outcome = self._hook_manager.run_hooks(HookEvent.STOP)
                if stop_outcome.blocked:
                    _debug_log("[HOOK] Stop hook blocked — would continue loop")
                    # Note: We can't re-enter the loop from here since we've
                    # already exited the while-loop. The Stop hook blocking
                    # is logged but the agent has already committed to stopping.
                    # Future: could set a flag for the next execution.

        # Play finish sound if enabled and NOT interrupted
        if getattr(self.config, "enable_sound", False) and not interrupted:
            play_finish_sound()

        return (self._last_operation_summary, self._last_error, self._last_latency_ms)

    def _build_messages_with_system_prompt(
        self, messages: list, system_prompt: str, *, exclude_nudges: bool = False
    ) -> list:
        """Clone messages and replace the system prompt.

        Both thinking and main phases use this to build their message arrays
        from the same compacted base messages.

        Args:
            messages: Source message list.
            system_prompt: System prompt to set as first message.
            exclude_nudges: If True, drop messages tagged with ``_nudge=True``.
        """
        result = list(messages)  # shallow clone
        if exclude_nudges:
            result = [m for m in result if not m.get("_nudge")]
        if result and result[0].get("role") == "system":
            result[0] = {"role": "system", "content": system_prompt}
        else:
            result.insert(0, {"role": "system", "content": system_prompt})
        return result

    def _maybe_compact(self, ctx: IterationContext) -> None:
        """Staged context optimization as usage grows.

        Stages:
        - 70%: Warning logged
        - 80%: Progressive observation masking (old tool results -> compact refs)
        - 90%: Aggressive masking (only recent 3 tool results kept)
        - 99%: Full LLM-powered compaction
        """
        if self._compactor is None:
            from opendev.core.context_engineering.compaction import ContextCompactor

            self._compactor = ContextCompactor(self.config, ctx.agent._http_client)

        # Set session ID for scratch file paths
        session = self.session_manager.get_current_session()
        if session is not None:
            self._compactor._session_id = session.id

        system_prompt = ctx.agent.system_prompt

        # Check staged optimization level
        from opendev.core.context_engineering.compaction import OptimizationLevel

        level = self._compactor.check_usage(ctx.messages, system_prompt)

        # Push context usage % to UI
        self._push_context_usage(ctx)

        # Apply progressive observation masking at 80% and 90%
        if level in (OptimizationLevel.MASK, OptimizationLevel.AGGRESSIVE):
            self._compactor.mask_old_observations(ctx.messages, level)

        # Fast pruning at 85%: strip old tool outputs (cheaper than LLM compaction)
        if level == OptimizationLevel.PRUNE:
            self._compactor.prune_old_tool_outputs(ctx.messages)

        # Full compaction at 99% or manual /compact
        should = self._force_compact_next or level == OptimizationLevel.COMPACT

        if should:
            self._force_compact_next = False
            before_count = len(ctx.messages)
            compacted = self._compactor.compact_with_retry(ctx.messages, system_prompt)
            ctx.messages[:] = compacted  # Mutate in-place
            after_count = len(ctx.messages)
            logger.info("Compacted %d messages -> %d", before_count, after_count)
            # Store compaction point in session metadata (like /compact)
            if session is not None:
                summary_msg = next(
                    (
                        m
                        for m in compacted
                        if m.get("content", "").startswith("[CONVERSATION SUMMARY]")
                    ),
                    None,
                )
                if summary_msg:
                    session.metadata["compaction_point"] = {
                        "summary": summary_msg["content"],
                        "at_message_count": len(session.messages),
                    }
                    self.session_manager.save_session()
            if ctx.ui_callback and hasattr(ctx.ui_callback, "on_message"):
                ctx.ui_callback.on_message(
                    f"Context auto-compacted ({before_count} -> {after_count} messages)"
                )

    def _push_context_usage(self, ctx: IterationContext) -> None:
        """Push current context usage percentage to the UI (best-effort)."""
        try:
            if self._compactor and ctx.ui_callback and hasattr(ctx.ui_callback, "on_context_usage"):
                pct = self._compactor.usage_pct
                new_msg = len(ctx.messages) - self._compactor._msg_count_at_calibration
                _ctx_logger.info(
                    "context_usage_push: pct=%.2f last_tok=%d max_ctx=%d "
                    "api_prompt_tok=%d msg_count_at_cal=%d cur_msg_count=%d new_msgs=%d",
                    pct,
                    self._compactor._last_token_count,
                    self._compactor._max_context,
                    self._compactor._api_prompt_tokens,
                    self._compactor._msg_count_at_calibration,
                    len(ctx.messages),
                    max(0, new_msg),
                )
                _session_debug().log(
                    "context_usage_push",
                    "compaction",
                    usage_pct=pct,
                    last_token_count=self._compactor._last_token_count,
                    max_context=self._compactor._max_context,
                    api_prompt_tokens=self._compactor._api_prompt_tokens,
                    msg_count_at_cal=self._compactor._msg_count_at_calibration,
                )
                ctx.ui_callback.on_context_usage(pct)
                # Persist for session resume
                session = self.session_manager.get_current_session()
                if session is not None:
                    session.metadata["context_usage_pct"] = round(pct, 1)
        except Exception as exc:
            logger.debug("_push_context_usage failed: %s", exc)

    def _display_message(self, message: str, ui_callback, dim: bool = False):
        """Display a message via UI callback or console."""
        if not message:
            return

        if ui_callback and hasattr(ui_callback, "on_assistant_message"):
            ui_callback.on_assistant_message(message)
        elif self.console:
            style = "[dim]" if dim else ""
            end_style = "[/dim]" if dim else ""
            self.console.print(f"\n{style}{message}{end_style}")
