from __future__ import annotations

import os
from typing import Any, Dict, List
import re

import httpx


TOOL_NAME = "perplexity_search"


def _call_perplexity(query: str, *, model: str, temperature: float = 0.2, max_tokens: int = 600) -> Dict[str, Any]:
    api_key = os.getenv("PPLX_API_KEY")
    if not api_key:
        raise RuntimeError("PPLX_API_KEY is not set. Add it to your environment to enable Perplexity searches.")

    endpoint = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a web search assistant. Answer concisely and include citations. Only use reliable sources. "
                    "Refuse and do not search for pornographic/sexually explicit content, gore/graphic violence, or illegal content. "
                    "If the user requests such content, politely decline in one short sentence."
                ),
            },
            {"role": "user", "content": query},
        ],
        "temperature": max(0.0, min(2.0, float(temperature))),
        "max_tokens": max(64, int(max_tokens)),
        "top_p": 1.0,
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(endpoint, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


def _extract_answer_and_sources(obj: Dict[str, Any]) -> str:
    # Try typical OpenAI-style choices
    content = ""
    citations: List[str] = []

    try:
        choices = obj.get("choices") or []
        if choices:
            message = choices[0].get("message", {})
            content = (message.get("content") or "").strip()
            # Perplexity sometimes returns citations either on the message or top-level
            msg_citations = message.get("citations") or []
            if isinstance(msg_citations, list):
                citations.extend([str(c) for c in msg_citations if isinstance(c, (str,))])
    except Exception:
        pass

    top_citations = obj.get("citations")
    if isinstance(top_citations, list):
        citations.extend([str(c) for c in top_citations if isinstance(c, (str,))])

    # De-duplicate while preserving order
    seen = set()
    deduped: List[str] = []
    for c in citations:
        if c not in seen:
            seen.add(c)
            deduped.append(c)

    if deduped:
        src_block = "\n".join(deduped[:5])
        return f"{content}\n\nSources:\n{src_block}" if content else f"Sources:\n{src_block}"
    return content or "No result."


schema: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Perform an internet search using Perplexity and return a concise answer with sources. "
            "Refuse and do NOT search if the query is pornographic/sexually explicit, contains gore/graphic violence, "
            "or requests illegal content. Politely decline in one short sentence."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to answer, phrased as a question or keywords.",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Perplexity online model to use (e.g., 'sonar-small-online', 'sonar-medium-online'). "
                        "Defaults to PPLX_MODEL env or 'sonar-small-online'."
                    ),
                },
                "temperature": {
                    "type": "number",
                    "description": "Sampling temperature (0-2). Lower is more deterministic.",
                    "minimum": 0,
                    "maximum": 2,
                    "default": 0.2,
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Max tokens in the answer (min 64).",
                    "minimum": 64,
                    "default": 600,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def execute(arguments: Dict[str, Any]) -> str:
    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ValueError("'query' is required")

    # Simple content safety check to block disallowed categories
    banned_patterns = [
        r"\b(porn|pornographic|xxx|nsfw|hentai|erotic|nud(e|ity)|sexual|sex)\b",
        r"\b(gore|gory|snuff|beheading|decapitation|dismemberment|graphic violence)\b",
        r"\b(illegal|contraband|child\s*porn|cp\b)\b",
    ]
    ql = query.lower()
    if any(re.search(pat, ql) for pat in banned_patterns):
        return "Sorry, I can’t help with that request."

    model = str(arguments.get("model") or os.getenv("PPLX_MODEL", "sonar-small-online"))
    temperature = float(arguments.get("temperature", 0.2))
    max_tokens = int(arguments.get("max_tokens", 600))

    try:
        data = _call_perplexity(query, model=model, temperature=temperature, max_tokens=max_tokens)
    except Exception as exc:  # pragma: no cover
        return f"Perplexity error: {exc}"

    return _extract_answer_and_sources(data)


__all__ = ["TOOL_NAME", "schema", "execute"]


