"""Core functionality for OpenDev."""

import os
import warnings
from importlib import import_module
from typing import Dict, Tuple

# Suppress transformers warning about missing ML frameworks
# OpenDev uses LLM APIs directly and doesn't need local models
os.environ["TRANSFORMERS_VERBOSITY"] = "error"  # Only show errors, not warnings
warnings.filterwarnings("ignore", message=".*None of PyTorch, TensorFlow.*found.*")
warnings.filterwarnings("ignore", message=".*Models won't be available.*")

__all__ = [
    "ConfigManager",
    "SessionManager",
    "MainAgent",
    "ModeManager",
    "OperationMode",
    "ApprovalManager",
    "ApprovalChoice",
    "ApprovalResult",
    "ErrorHandler",
    "ErrorAction",
    "UndoManager",
    "ToolRegistry",
]

_EXPORTS: Dict[str, Tuple[str, str]] = {
    "MainAgent": ("opendev.core.agents", "MainAgent"),
    "ConfigManager": ("opendev.core.runtime", "ConfigManager"),
    "SessionManager": ("opendev.core.context_engineering.history", "SessionManager"),
    "ModeManager": ("opendev.core.runtime", "ModeManager"),
    "OperationMode": ("opendev.core.runtime", "OperationMode"),
    "UndoManager": ("opendev.core.context_engineering.history", "UndoManager"),
    "ApprovalManager": ("opendev.core.runtime.approval", "ApprovalManager"),
    "ApprovalChoice": ("opendev.core.runtime.approval", "ApprovalChoice"),
    "ApprovalResult": ("opendev.core.runtime.approval", "ApprovalResult"),
    "ErrorHandler": ("opendev.core.runtime.monitoring", "ErrorHandler"),
    "ErrorAction": ("opendev.core.runtime.monitoring", "ErrorAction"),
    "ToolRegistry": ("opendev.core.context_engineering.tools", "ToolRegistry"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module 'opendev.core' has no attribute '{name}'")
    module_path, attr_name = _EXPORTS[name]
    module = import_module(module_path)
    attr = getattr(module, attr_name)
    globals()[name] = attr
    return attr
