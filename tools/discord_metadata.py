from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Tuple

from tools import tool


API_BASE = "https://discord.com/api/v10"


def _get_bot_token() -> str | None:
    env = (os.getenv("ENVIRONMENT", "production") or "").lower()
    token_env = "DISCORD_TOKEN_DEV" if env == "development" else "DISCORD_TOKEN"
    token = os.getenv(token_env) or os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_TOKEN_DEV")
    return token


def _http_request(method: str, path: str, query: Dict[str, Any] | None = None) -> Tuple[int, Dict[str, Any]]:
    """Minimal REST helper for Discord API.

    Returns (status_code, json_dict). Handles basic 429 retry.
    """
    token = _get_bot_token()
    if not token:
        return 0, {"error": "Missing Discord bot token in environment"}

    url = f"{API_BASE}{path}"
    if query:
        qs = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        url = f"{url}?{qs}"

    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "PorygonBot (discord.py tools, metadata)",
        "Accept": "application/json",
    }

    data_bytes = None
    req = urllib.request.Request(url, headers=headers, method=method.upper(), data=data_bytes)

    # Basic retry on rate limit
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = getattr(resp, "status", 200)
                text = resp.read().decode("utf-8") or "{}"
                try:
                    return status, json.loads(text)
                except Exception:
                    return status, {"raw": text}
        except urllib.error.HTTPError as e:
            status = getattr(e, "code", 0)
            body = e.read().decode("utf-8") if hasattr(e, "read") else "{}"
            try:
                payload = json.loads(body or "{}")
            except Exception:
                payload = {"raw": body}
            # 429 handling
            if status == 429:
                retry_after = 0.0
                try:
                    retry_after = float(payload.get("retry_after", 0))
                except Exception:
                    retry_after = 0.0
                time.sleep(min(max(retry_after, 0.0), 5.0))
                continue
            return status, payload
        except Exception as e:  # pragma: no cover
            return 0, {"error": str(e)}

    return 429, {"error": "Rate limited"}


def _get_channel(channel_id: str | int) -> Dict[str, Any] | None:
    status, data = _http_request("GET", f"/channels/{channel_id}")
    return data if status == 200 else None


def _get_guild_id_from_channel(channel_id: str | int | None) -> str | None:
    if not channel_id:
        return None
    info = _get_channel(channel_id)
    if not info:
        return None
    gid = info.get("guild_id")
    return str(gid) if gid else None


def _get_guild_member(guild_id: str, user_id: str) -> Dict[str, Any] | None:
    status, data = _http_request("GET", f"/guilds/{guild_id}/members/{user_id}")
    return data if status == 200 else None


def _get_message(channel_id: str, message_id: str) -> Dict[str, Any] | None:
    status, data = _http_request("GET", f"/channels/{channel_id}/messages/{message_id}")
    return data if status == 200 else None


def _extract_message_text_from_payload(msg: Dict[str, Any]) -> str:
    try:
        content = (msg.get("content") or "").strip()
        if content:
            return content
        parts: List[str] = []
        for e in (msg.get("embeds") or []):
            title = e.get("title")
            desc = e.get("description")
            if title:
                parts.append(str(title))
            if desc:
                parts.append(str(desc))
            for f in (e.get("fields") or []):
                name = f.get("name", "")
                value = f.get("value", "")
                if name or value:
                    parts.append(f"{name}: {value}")
        return " ".join(p for p in parts if p).strip()
    except Exception:
        return ""


@tool("discord_server_profile_name")
def discord_server_profile_name(discord_user_id: str, channel_id: str | None = None) -> str:
    """Return the user's server profile display name (nickname) if available; otherwise a global display name.

    Args:
        discord_user_id: The target user's Discord ID.
        channel_id: The channel context (used to infer the guild).
    """
    uid = (discord_user_id or "").strip()
    if not uid:
        return ""
    gid = _get_guild_id_from_channel(channel_id)
    if not gid:
        return ""  # Not in a guild context
    member = _get_guild_member(gid, uid)
    if not member:
        return ""
    # Prefer server nickname, then global display name, then username
    nick = member.get("nick") or ""
    user = member.get("user") or {}
    global_name = user.get("global_name") or ""
    username = user.get("username") or ""
    display = nick or global_name or username
    return str(display or "")


@tool("discord_username")
def discord_username(discord_user_id: str, channel_id: str | None = None) -> str:
    """Return the user's username within the current server context.

    Args:
        discord_user_id: The target user's unique Discord identifer. Numeric, prepended to each user's message.
        channel_id: The channel context (used to infer the guild).
    """
    uid = (discord_user_id or "").strip()
    if not uid:
        return ""
    gid = _get_guild_id_from_channel(channel_id)
    if not gid:
        return ""
    member = _get_guild_member(gid, uid)
    if not member:
        return ""
    user = member.get("user") or {}
    username = user.get("username") or user.get("global_name") or ""
    return str(username or "")


@tool("discord_message_content")
def discord_message_content(message_id: str, channel_id: str | None = None) -> str:
    """Return the content (or embed text) of a message in the current channel.

    Args:
        message_id: The message ID to fetch.
        channel_id: The channel context containing the message.
    """
    mid = (message_id or "").strip()
    if not mid or not channel_id:
        return ""
    msg = _get_message(str(channel_id), mid)
    if not msg:
        return ""
    return _extract_message_text_from_payload(msg)


def _iter_channel_messages(channel_id: str, max_to_scan: int = 200) -> Iterable[Dict[str, Any]]:
    remaining = max(0, int(max_to_scan))
    before: str | None = None
    while remaining > 0:
        limit = min(100, remaining)
        query = {"limit": limit}
        if before:
            query["before"] = before
        status, data = _http_request("GET", f"/channels/{channel_id}/messages", query)
        if status != 200 or not isinstance(data, list):
            break
        if not data:
            break
        for msg in data:
            yield msg
        remaining -= len(data)
        before = str(data[-1].get("id"))


@tool("discord_search_messages")
def discord_search_messages(
    keywords: List[str],
    channel_id: str | None = None,
    max_messages: int | None = 200,
    require_all: bool | None = True,
) -> str:
    """Search recent messages in the current channel by keywords. Returns JSON with matches.

    Args:
        keywords: List of keywords to match. By default, all must be present in the message.
        channel_id: The channel to search (defaults to current message channel).
        max_messages: Max recent messages to scan (across pages), up to 200 by default.
        require_all: If true, messages must contain all keywords; if false, any keyword.
    """
    if not channel_id:
        return json.dumps({"matches": []})
    words = [w.strip() for w in (keywords or []) if isinstance(w, str) and w.strip()]
    if not words:
        return json.dumps({"matches": []})
    mode_all = bool(require_all if require_all is not None else True)
    max_scan = int(max_messages or 200)

    words_lower = [w.lower() for w in words]
    matches: List[Dict[str, Any]] = []
    scanned = 0
    for msg in _iter_channel_messages(str(channel_id), max_to_scan=max_scan):
        scanned += 1
        text = _extract_message_text_from_payload(msg).lower()
        if not text:
            continue
        present = [(w in text) for w in words_lower]
        if (all(present) if mode_all else any(present)):
            matches.append({
                "id": str(msg.get("id")),
                "author_id": str((msg.get("author") or {}).get("id", "")),
                "content": _extract_message_text_from_payload(msg),
                "timestamp": msg.get("timestamp"),
            })
        if len(matches) >= 25:
            break

    return json.dumps({"matches": matches})


@tool("discord_guild_emojis")
def discord_guild_emojis(channel_id: str | None = None) -> str:
    """Return a JSON list of emojis for the current server (name, id, animated, mention).

    Args:
        channel_id: The channel context (used to infer the guild).
    """
    gid = _get_guild_id_from_channel(channel_id)
    if not gid:
        return json.dumps([])
    status, data = _http_request("GET", f"/guilds/{gid}/emojis")
    if status != 200 or not isinstance(data, list):
        return json.dumps([])
    out: List[Dict[str, Any]] = []
    for e in data:
        eid = str(e.get("id"))
        name = e.get("name") or ""
        animated = bool(e.get("animated", False))
        mention = f"<{'a:' if animated else ':'}{name}:{eid}>"
        out.append({
            "name": name,
            "id": eid,
            "animated": animated,
            "mention": mention,
        })
    return json.dumps(out)


__all__ = [
    "discord_server_profile_name",
    "discord_username",
    "discord_message_content",
    "discord_search_messages",
    "discord_guild_emojis",
]


