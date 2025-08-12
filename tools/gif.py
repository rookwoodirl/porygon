from __future__ import annotations

import os
import random
from typing import Any, Dict, List
import re

import httpx

from tools import tool


TOOL_NAME = "gif"


def _search_tenor(query: str, limit: int = 25, locale: str | None = None) -> List[str]:
    """Search Tenor for GIFs and return a list of GIF URLs.
    Can be used for reactions to things."""
    api_key = os.getenv("TENOR_API_KEY", "LIVDSRZULELA")  # public demo key
    params = {
        "q": query,
        "key": api_key,
        "limit": max(1, min(limit, 50)),
        "media_filter": "gif",
    }
    if locale:
        params["locale"] = locale

    url = "https://tenor.googleapis.com/v2/search"
    with httpx.Client(timeout=10) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = []
    for item in data.get("results", []):
        # Tenor v2 format: item["media_formats"]["gif"]["url"]
        media = item.get("media_formats", {})
        gif_obj = media.get("gif") or media.get("tinygif") or media.get("nanogif")
        if isinstance(gif_obj, dict):
            url = gif_obj.get("url")
            if isinstance(url, str):
                results.append(url)
    return results


@tool(TOOL_NAME)
def gif(query: str, limit: int = 25, locale: str | None = None) -> str:
    """Search for a GIF and return a shareable GIF URL (Discord will auto-embed).

    query: Search terms for the GIF (e.g., 'excited cat').
    limit: Max number of results to consider (1-50).
    locale: BCP-47 language code for localized results (e.g., 'en', 'es').
    """
    q = str(query or "").strip()
    if not q:
        raise ValueError("'query' is required")

    banned_patterns = [
        r"\b(porn|pornographic|xxx|nsfw|hentai|erotic|nud(e|ity)|sexual|sex)\b",
        r"\b(gore|gory|snuff|beheading|decapitation|dismemberment|graphic violence)\b",
        r"\b(illegal|contraband|child\s*porn|cp\b)\b",
    ]
    ql = q.lower()
    if any(re.search(pat, ql) for pat in banned_patterns):
        return "Sorry, I can’t help with that request."

    try:
        urls = _search_tenor(query=q, limit=int(limit), locale=locale)
    except Exception as exc:  # pragma: no cover
        return f"Failed to search GIFs: {exc}"

    if not urls:
        return f"No GIFs found for: {query}"

    # Pick one at random for variety
    return random.choice(urls)


__all__ = ["TOOL_NAME", "gif"]


