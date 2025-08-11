from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Callable, Dict, List
import inspect


# Registry of tool functions. Keys are tool names, values are callables.
TOOL_FUNCTIONS: Dict[str, Callable[..., str]] = {}


def tool(name: str) -> Callable[[Callable[..., str]], Callable[..., str]]:
    """Decorator to register a function as a tool available to contexts.

    The function's docstring will be used by contexts to build schemas dynamically.
    """

    def _decorator(fn: Callable[..., str]) -> Callable[..., str]:
        TOOL_FUNCTIONS[name] = fn
        return fn

    return _decorator


def _import_tool_modules() -> None:
    package_name = __name__
    package_path_list = list(getattr(__import__(package_name), "__path__", [])) or [str(Path(__file__).parent)]
    for _, mod_name, is_pkg in pkgutil.iter_modules(package_path_list):
        if is_pkg or mod_name.startswith("_") or mod_name == "__init__":
            continue
        try:
            importlib.import_module(f"{package_name}.{mod_name}")
        except Exception:
            # Ignore faulty modules; tools from others still register
            continue


# Import tool modules at import time so @tool decorators run
_import_tool_modules()


def get_tool_functions(names: List[str] | None = None) -> Dict[str, Callable[..., str]]:
    if names is None:
        return dict(TOOL_FUNCTIONS)
    return {n: TOOL_FUNCTIONS[n] for n in names if n in TOOL_FUNCTIONS}


def _function_to_schema(name: str, fn: Callable[..., str]) -> dict:
    doc = inspect.getdoc(fn) or "Perform an action"
    sig = inspect.signature(fn)
    props: Dict[str, dict] = {}
    required: List[str] = []
    for param_name, param in sig.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        props[param_name] = {"type": "string", "description": f"Argument {param_name}"}
        if param.default is inspect._empty:
            required.append(param_name)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": doc,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def get_tool_schemas(tool_names: List[str]) -> List[dict]:
    funcs = get_tool_functions(tool_names)
    return [_function_to_schema(name, fn) for name, fn in funcs.items()]


__all__ = ["tool", "get_tool_functions", "get_tool_schemas", "TOOL_FUNCTIONS"]

