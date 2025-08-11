from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Dict

# Global registry of tool functions: name -> callable
TOOL_FUNCTIONS: Dict[str, Callable[..., Any]] = {}


def tool(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a function as a tool under the given name.

    The function's docstring will be used elsewhere (e.g., in contexts)
    to build an OpenAI tool schema dynamically.
    """

    def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        TOOL_FUNCTIONS[name] = fn
        return fn

    return _decorator


__all__ = ["tool", "TOOL_FUNCTIONS"]

