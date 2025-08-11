from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Account


_SessionFactory: Optional[sessionmaker] = None


def _get_session_factory() -> Optional[sessionmaker]:
    global _SessionFactory
    if _SessionFactory is not None:
        return _SessionFactory
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return None
    try:
        engine = create_engine(dsn, future=True)
        _SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    except Exception:
        _SessionFactory = None
    return _SessionFactory


def link_puuid_to_discord(puuid: str, discord_id: str) -> bool:
    """Link a Riot PUUID to a Discord user id in the Accounts table.

    Returns True if a row exists after the operation (created or already present), False on failure or no DB.
    """
    sf = _get_session_factory()
    if not sf:
        return False
    try:
        with sf() as s:
            existing = s.get(Account, {"discord_id": discord_id, "puuid": puuid})
            if existing:
                return True
            s.add(Account(discord_id=discord_id, puuid=puuid))
            s.commit()
            return True
    except Exception:
        return False

