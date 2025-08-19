from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Callable, Dict, List
import inspect

# Parameter names considered private metadata and should not be exposed to the model in tool schemas.
# Tools may still accept these parameters and the bot can inject them locally, but they will be hidden
# from the OpenAI-visible function schema so the model won't know to request them.
PRIVATE_METADATA_KEYS = {
    "author_id",
    "message_id",
    "channel_id",
    "attachments",
}


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
    doc = inspect.getdoc(fn).split('Args')[0].strip() or "Perform an action"
    sig = inspect.signature(fn)
    props: Dict[str, dict] = {}
    required: List[str] = []
    # Try to extract parameter descriptions from the function docstring. Expected simple format:
    #   param_name: description
    param_descriptions: Dict[str, str] = {}
    try:
        for line in (doc or "").splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            parts = line.split(":", 1)
            key = parts[0].strip()
            if not key or not key.isidentifier():
                continue
            param_descriptions[key] = parts[1].strip()
    except Exception:
        param_descriptions = {}

    def _annotation_to_json_type(annotation: object) -> str:
        try:
            if annotation is inspect._empty:
                return "string"
            # Handle common builtin types
            if annotation in (str,):
                return "string"
            if annotation in (int,):
                return "integer"
            if annotation in (float,):
                return "number"
            if annotation in (bool,):
                return "boolean"
            if annotation in (list, tuple, set):
                return "array"
            if annotation in (dict,):
                return "object"
            ann_name = getattr(annotation, "__name__", str(annotation)).lower()
            if "list" in ann_name or "tuple" in ann_name:
                return "array"
            if "dict" in ann_name or "mapping" in ann_name or "object" in ann_name:
                return "object"
        except Exception:
            pass
        return "string"

    def _annotation_allows_none(annotation: object) -> bool:
        """Return True if the annotation allows None (Optional/Union[..., None], or X | None)."""
        try:
            if annotation is inspect._empty:
                return False
            # Use typing.get_args which works for Optional, Union, and PEP 604 (X | None)
            try:
                from typing import get_args
                args = get_args(annotation)
            except Exception:
                args = ()
            return any(a is type(None) for a in args)
        except Exception:
            return False

    for param_name, param in sig.parameters.items():
        # Do not expose private metadata parameters in the schema sent to the model
        if param_name in PRIVATE_METADATA_KEYS:
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        ann = param.annotation if param.annotation is not inspect._empty else inspect._empty
        json_type = _annotation_to_json_type(ann)
        desc = param_descriptions.get(param_name, f"Argument {param_name}")
        schema_prop = {"type": json_type, "description": desc}
        if json_type == "array":
            # Provide a default item type to satisfy OpenAI function schema requirements
            schema_prop["items"] = {"type": "string"}
        props[param_name] = schema_prop
        if param.default is inspect._empty and not _annotation_allows_none(ann):
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

TOOL_SCHEMAS = get_tool_schemas(get_tool_functions())


__all__ = ["tool", "TOOL_FUNCTIONS", "TOOL_SCHEMAS"]

