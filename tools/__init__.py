from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Callable, Dict, List


class ToolSpec:
    def __init__(self, schema: dict, execute: Callable[[dict], str]):
        self.schema = schema
        self.execute = execute


def _discover_tools() -> Dict[str, ToolSpec]:
    registry: Dict[str, ToolSpec] = {}

    package_name = __name__  # e.g., "tools"
    package_path_list = list(getattr(__import__(package_name), "__path__", []))

    # Fallback to filesystem scan in case __path__ is not set (edge cases)
    if not package_path_list:
        package_path_list = [str(Path(__file__).parent)]

    # Iterate immediate modules in this package
    for finder, mod_name, is_pkg in pkgutil.iter_modules(package_path_list):
        if is_pkg:
            continue
        if mod_name.startswith("_") or mod_name == "__init__":
            continue

        full_name = f"{package_name}.{mod_name}"
        try:
            module = importlib.import_module(full_name)
        except Exception:
            continue

        tool_name = getattr(module, "TOOL_NAME", None)
        schema = getattr(module, "schema", None)
        execute = getattr(module, "execute", None)

        if not isinstance(tool_name, str) or not isinstance(schema, dict) or not callable(execute):
            continue

        registry[tool_name] = ToolSpec(schema=schema, execute=execute)

    return registry


# Registry maps tool function name -> ToolSpec (built dynamically)
TOOL_REGISTRY: Dict[str, ToolSpec] = _discover_tools()


def get_tool_schemas(tool_names: List[str] | None = None) -> List[dict]:
    if tool_names is None:
        return [spec.schema for spec in TOOL_REGISTRY.values()]
    schemas: List[dict] = []
    for name in tool_names:
        spec = TOOL_REGISTRY.get(name)
        if spec:
            schemas.append(spec.schema)
    return schemas


__all__ = ["TOOL_REGISTRY", "get_tool_schemas", "ToolSpec"]

