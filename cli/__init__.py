"""Command-line interface entry point for OpenDev."""

from opendev.cli.main import main
from opendev.cli.non_interactive import _run_non_interactive

__all__ = ["main", "_run_non_interactive"]
