from __future__ import annotations

import json
import os
from typing import Any

from sqlalchemy import create_engine
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
    if sf:
        with sf() as s:
            row = s.get(LOLMatch, match_id)
            if row:
                return json.dumps(row.match_data, ensure_ascii=False)
    data = _client().lol_get_match(match_id)
    return json.dumps(data, ensure_ascii=False)


@tool("riot_tft_match")
def riot_tft_match(match_id: str) -> str:
    """Get a TFT match by id (cache-first). Returns JSON string.

    Args:
      match_id: Riot match id"""
    sf = _session_factory()
    if sf:
        with sf() as s:
            row = s.get(TFTMatch, match_id)
            if row:
                return json.dumps(row.match_data, ensure_ascii=False)
    data = _client().tft_get_match(match_id)
    return json.dumps(data, ensure_ascii=False)


@tool("riot_summoner_by_puuid")
def riot_summoner_by_puuid(puuid: str) -> str:
    """Get a summoner by PUUID (cache-first; LoL then TFT). Returns JSON string.

    Args:
      puuid: Summoner PUUID"""
    sf = _session_factory()
    if sf:
        with sf() as s:
            row = s.get(Summoner, puuid)
            if row:
                return json.dumps(
                    {
                        "puuid": row.puuid,
                        "profileIconId": row.profile_icon_id,
                        "revisionDate": row.revision_date,
                        "summonerLevel": row.summoner_level,
                        "created_at": row.created_at.isoformat(),
                    },
                    ensure_ascii=False,
                )
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



