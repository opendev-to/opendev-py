"""Background process management for bash tool."""

import subprocess
import time
from typing import Optional


class ProcessMixin:
    """Mixin for background process management.

    Expects the composing class to have a ``_background_processes`` dict
    and the security methods ``_is_command_allowed`` / ``_is_dangerous``
    (provided by :class:`SecurityMixin`).
    """

    def list_processes(self) -> list[dict]:
        """List all tracked background processes.

        Returns:
            List of process info dicts with pid, command, status, runtime
        """
        processes = []
        for pid, info in list(self._background_processes.items()):
            process = info["process"]
            status = "running" if process.poll() is None else "finished"
            runtime = time.time() - info["start_time"]

            processes.append({
                "pid": pid,
                "command": info["command"],
                "status": status,
                "runtime": runtime,
                "exit_code": process.returncode if status == "finished" else None,
            })

        return processes

    def get_process_output(self, pid: int) -> dict:
        """Get output from a background process.

        Args:
            pid: Process ID

        Returns:
            Dict with stdout, stderr, status, exit_code
        """
        if pid not in self._background_processes:
            return {
                "success": False,
                "error": f"Process {pid} not found",
            }

        info = self._background_processes[pid]
        process = info["process"]

        # Just return what's already captured - don't try to read more
        # (readline() blocks on pipes for long-running servers)
        # Output was already captured at process start

        # Check if process finished
        return_code = process.poll()
        status = "running" if return_code is None else "finished"

        return {
            "success": True,
            "pid": pid,
            "command": info["command"],
            "status": status,
            "exit_code": return_code,
            "stdout": "".join(info["stdout_lines"]),  # Return all captured output
            "stderr": "".join(info["stderr_lines"]),
            "total_stdout": "".join(info["stdout_lines"]),
            "total_stderr": "".join(info["stderr_lines"]),
            "runtime": time.time() - info["start_time"],
        }

    def kill_process(self, pid: int, signal: int = 15) -> dict:
        """Kill a background process.

        Args:
            pid: Process ID
            signal: Signal to send (default: 15/SIGTERM)

        Returns:
            Dict with success status
        """
        if pid not in self._background_processes:
            return {
                "success": False,
                "error": f"Process {pid} not found",
            }

        info = self._background_processes[pid]
        process = info["process"]

        try:
            if signal == 9:
                process.kill()  # SIGKILL
            else:
                process.terminate()  # SIGTERM

            # Wait for process to finish
            process.wait(timeout=5)

            # Clean up
            del self._background_processes[pid]

            return {
                "success": True,
                "pid": pid,
                "message": f"Process {pid} terminated",
            }

        except subprocess.TimeoutExpired:
            # Force kill if terminate didn't work
            process.kill()
            del self._background_processes[pid]

            return {
                "success": True,
                "pid": pid,
                "message": f"Process {pid} force killed",
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to kill process {pid}: {str(e)}",
            }

    def preview_command(self, command: str, working_dir: Optional[str] = None) -> str:
        """Generate a preview of the command execution.

        Args:
            command: Command to preview
            working_dir: Working directory

        Returns:
            Formatted preview string
        """
        work_dir = working_dir or str(self.working_dir)

        preview = f"Command: {command}\n"
        preview += f"Working Directory: {work_dir}\n"
        preview += f"Timeout: {self.config.bash_timeout}s\n"

        # Safety checks
        if not self._is_command_allowed(command):
            preview += "\n⚠️  WARNING: Command not in allowed list\n"

        if self._is_dangerous(command):
            preview += "\n❌ DANGER: Command matches dangerous pattern\n"

        return preview
