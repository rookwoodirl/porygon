from __future__ import annotations

import json
import os

from tools import tool
from util.accounts import link_puuid_to_discord as _link
from db.models import Summoner
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


def _session_factory() -> sessionmaker | None:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return None
    try:
        engine = create_engine(dsn, future=True)
        return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    except Exception:
        return None

@tool("link_puuid_to_discord")
def link_puuid_to_discord(puuid: str, author_id: str | None = None) -> str:
    """Link a Riot PUUID to a Discord user id in the Accounts table.

    Args:
      puuid: Riot PUUID to link

    Returns a JSON object: {"ok": true/false}
    """
    ok = _link(puuid, author_id)
    return json.dumps({"ok": ok})


@tool("get_puuid_by_discord_id")
def get_puuid_by_discord_id(discord_id : str | None = None, author_id: str | None = None) -> str:
    """Lookup puuids associated with a Discord user id from the Summoner table.

    Args:
      discord_id: Discord user id as string

    Returns:
      JSON array (string) of puuids associated with that discord id.
    """

    discord_id = discord_id or author_id

    sf = _session_factory()
    if not sf:
        return json.dumps([], ensure_ascii=False)
    try:
        with sf() as s:
            rows = s.scalars(select(Summoner).where(Summoner.discord_id == discord_id)).all()
            puuids = [r.puuid for r in rows] if rows else []
            return json.dumps(puuids, ensure_ascii=False)
    except Exception:
        return json.dumps([], ensure_ascii=False)

