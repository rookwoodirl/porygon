from __future__ import annotations

import os
from typing import Any, Dict, List
import re

import httpx

from tools import tool




def _call_perplexity(query: str) -> Dict[str, Any]:
    api_key = os.getenv("PPLX_API_KEY")
    if not api_key:
        raise RuntimeError("PPLX_API_KEY is not set. Add it to your environment to enable Perplexity searches.")

    endpoint = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": 'sonar',
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
        ]
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(endpoint, headers=headers, json=payload)
        # If the API returns an error, include the body to help debugging
        if resp.status_code != 200:
            body = None
            try:
                body = resp.text
            except Exception:
                body = '<unreadable body>'
            raise RuntimeError(f"Perplexity API error {resp.status_code}: {body}")
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


@tool('perplexity_search')
def perplexity_search(query: str, model: str | None = None, temperature: float = 0.2, max_tokens: int = 600) -> str:
    """Perform an internet search using Perplexity and return a concise answer with sources.

    query: The search query to answer, phrased as a question or keywords.
    model: Perplexity online model to use (e.g., 'sonar-small-online'). Defaults to PPLX_MODEL env.
    temperature: Sampling temperature (0-2). Lower is more deterministic.
    max_tokens: Max tokens in the answer (min 64).
    """
    q = str(query or "").strip()
    if not q:
        raise ValueError("'query' is required")

    # Simple content safety check to block disallowed categories
    banned_patterns = [
        r"\b(porn|pornographic|xxx|nsfw|hentai|erotic|nud(e|ity)|sexual|sex)\b",
        r"\b(gore|gory|snuff|beheading|decapitation|dismemberment|graphic violence)\b",
        r"\b(illegal|contraband|child\s*porn|cp\b)\b",
    ]
    ql = q.lower()
    if any(re.search(pat, ql) for pat in banned_patterns):
        return "Sorry, I can’t help with that request."

    try:
        data = _call_perplexity(q)
    except Exception as exc:  # pragma: no cover
        return f"Perplexity error: {exc}"

    return _extract_answer_and_sources(data)


__all__ = ["perplexity_search"]


