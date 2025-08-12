from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from tools import tool
from util.riot import RiotApiClient, RiotApiError
from db.models import Summoner, LOLMatch, TFTMatch


def _session_factory() -> sessionmaker | None:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return None
    try:
        engine = create_engine(dsn, future=True)
        return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    except Exception:
        return None


logger = logging.getLogger(__name__)


def _client() -> RiotApiClient:
    return RiotApiClient(
        api_key=os.getenv("RIOT_API_KEY"),
        platform=os.getenv("RIOT_PLATFORM", "na1"),
        region=os.getenv("RIOT_REGION", "americas"),
    )


@tool("riot_lol_match")
def riot_lol_match(match_id: str) -> str:
    """Get a League of Legends match by id (cache-first). Returns JSON string.

    Args:
      match_id: Riot match id, e.g., NA1_123..."""
    sf = _session_factory()
    if not sf:
        logger.warning("DATABASE_URL not set or session factory failed; skipping LOL match persistence")
    # cache-first: return DB copy if present
    if sf:
        try:
            with sf() as s:
                row = s.get(LOLMatch, match_id)
                if row:
                    return json.dumps(row.match_data, ensure_ascii=False)
        except Exception as e:
            logger.exception("Failed reading LOLMatch from DB: %s", e)

    data = _client().lol_get_match(match_id)

    return json.dumps(data, ensure_ascii=False)


@tool("riot_tft_match")
def riot_tft_match(match_id: str) -> str:
    """Get a TFT match by id (cache-first). Returns JSON string.

    Args:
      match_id: Riot match id"""
    sf = _session_factory()
    if not sf:
        logger.warning("DATABASE_URL not set or session factory failed; skipping TFT match persistence")
    if sf:
        try:
            with sf() as s:
                row = s.get(TFTMatch, match_id)
                if row:
                    return json.dumps(row.match_data, ensure_ascii=False)
        except Exception as e:
            logger.exception("Failed reading TFTMatch from DB: %s", e)

    data = _client().tft_get_match(match_id)

    return json.dumps(data, ensure_ascii=False)


@tool("riot_summoner_by_puuid")
def riot_summoner_by_puuid(puuid: str) -> str:
    """Get a summoner by PUUID (cache-first; LoL then TFT). Returns JSON string.

    Args:
      puuid: Summoner PUUID"""
    
    client = _client()
    try:
        data: Any = client.lol_get_summoner_by_puuid(puuid)
    except RiotApiError:
        data = client.tft_get_summoner_by_puuid(puuid)

    return json.dumps(data, ensure_ascii=False)


@tool("riot_account_by_riot_id")
def riot_account_by_riot_id(riot_id: str) -> str:
    """Get an account by Riot ID (name#tag). Returns JSON string.

    Args:
      riot_id: in the form 'name#tag'."""
    if "#" not in riot_id:
        raise ValueError("riot_id must be 'name#tag'")
    name, tag = riot_id.split("#", 1)
    client = _client()
    data = client.account_get_by_riot_id(name, tag)
    return json.dumps(data, ensure_ascii=False)




