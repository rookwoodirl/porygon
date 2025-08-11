from __future__ import annotations

import ast
import operator as op
from typing import Any, Dict


TOOL_NAME = "calculator"


# Safe eval of simple math expressions using AST
_operators = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.USub: op.neg,
    ast.Mod: op.mod,
    ast.FloorDiv: op.floordiv,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Num):  # type: ignore[attr-defined]
        return float(node.n)  # type: ignore[attr-defined]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _operators:
        return _operators[type(node.op)](_eval(node.operand))  # type: ignore[index]
    if isinstance(node, ast.BinOp) and type(node.op) in _operators:
        return _operators[type(node.op)](_eval(node.left), _eval(node.right))  # type: ignore[index]
    raise ValueError("Unsupported expression")


def _safe_eval_expr(expr: str) -> float:
    try:
        print(f'Calculating... {expr}')
        parsed = ast.parse(expr, mode="eval")
        return _eval(parsed.body)  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover
        raise ValueError(f"Invalid expression: {exc}")


schema: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "Evaluate a math expression safely. Supports +, -, *, /, **, %, and parentheses.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "A math expression, e.g., '(2 + 3) * 4 ** 2'",
                }
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
}


def execute(arguments: Dict[str, Any]) -> str:
    expr = str(arguments.get("expression", "")).strip()
    if not expr:
        raise ValueError("'expression' is required")
    value = _safe_eval_expr(expr)
    # Return as string for OpenAI tool output content
    return str(value)


__all__ = ["TOOL_NAME", "schema", "execute"]

