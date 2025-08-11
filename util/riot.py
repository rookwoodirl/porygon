from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

import httpx
import json
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from db.models import APILog, TFTMatch, LOLMatch, Summoner


class RiotApiError(RuntimeError):
    """Raised for anything other than 200-level OK stuff."""

    def __init__(self, status_code: int, message: str, *, response_json: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(f"Riot API error {status_code}: {message}")
        self.status_code = status_code
        self.response_json = response_json


# Platform routing (platform-specific endpoints)
# Full list: https://developer.riotgames.com/apis
PLATFORM_ROUTING: Dict[str, str] = {
    # Americas
    "na": "na1",
    "na1": "na1",
    "br": "br1",
    "br1": "br1",
    "lan": "la1",
    "la1": "la1",
    "las": "la2",
    "la2": "la2",
    "oce": "oc1",
    "oc1": "oc1",
    # Europe
    "euw": "euw1",
    "euw1": "euw1",
    "eune": "eun1",
    "eun1": "eun1",
    "tr": "tr1",
    "tr1": "tr1",
    "ru": "ru",
    # Asia
    "kr": "kr",
    "jp": "jp1",
    "jp1": "jp1",
}


# Regional routing (match endpoints)
REGIONAL_ROUTING: Dict[str, str] = {
    "americas": "americas",
    "europe": "europe",
    "asia": "asia",
    "sea": "sea",
}


def _normalize_platform(platform: str) -> str:
    key = (platform or "").lower()
    return PLATFORM_ROUTING.get(key, platform)


def _normalize_region(region: str) -> str:
    key = (region or "").lower()
    return REGIONAL_ROUTING.get(key, region)


@dataclass
class RiotApiClient:
    """Thin Riot API client with helpers for League and TFT endpoints."""

    api_key: str | None = None
    platform: str = "na1"
    region: str = "americas"
    timeout_seconds: float = 10.0
    database_url: Optional[str] = None

    def __post_init__(self) -> None:
        """This is called after __init__ and handles some simple setup."""
        if not self.api_key:
            self.api_key = os.getenv("RIOT_API_KEY")
        if not self.api_key:
            raise ValueError("RIOT_API_KEY not set. Provide api_key or set environment variable.")
        self.platform = _normalize_platform(self.platform)
        self.region = _normalize_region(self.region)
        self._client = httpx.Client(timeout=self.timeout_seconds)
        # Optional SQLAlchemy session factory for logging and match storage
        self.database_url = self.database_url or os.getenv("DATABASE_URL")
        self._Session: Optional[sessionmaker] = None
        if self.database_url:
            try:
                engine = create_engine(self.database_url, future=True)
                self._Session = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
            except Exception:
                # If DB init fails, proceed without persistence
                self._Session = None

    # ---------- low-level request helpers ----------
    def _platform_base(self) -> str:
        return f"https://{self.platform}.api.riotgames.com"

    def _region_base(self) -> str:
        return f"https://{self.region}.api.riotgames.com"

    def _headers(self) -> Dict[str, str]:
        return {"X-Riot-Token": self.api_key or ""}

    def _get_json(self, url: str, params: Optional[Mapping[str, Any]] = None, *, retry: int = 2) -> Any:
        for attempt in range(retry + 1):
            resp = self._client.get(url, headers=self._headers(), params=params)
            if resp.status_code == 429 and attempt < retry:
                # Respect Retry-After if present
                retry_after = 0
                try:
                    retry_after = int(resp.headers.get("Retry-After", "0"))
                except Exception:
                    retry_after = 1
                time.sleep(max(1, retry_after))
                continue
            if 200 <= resp.status_code < 300:
                return resp.json()
            # Raise informative error
            try:
                data = resp.json()
            except Exception:
                data = None
            raise RiotApiError(resp.status_code, resp.text, response_json=data)
        # Should not reach
        raise RiotApiError(429, "Rate limit retries exceeded")

    # ---------- persistence helpers ----------
    def _log_api(self, *, endpoint: str, params: Optional[Mapping[str, Any]], full_url: str) -> None:
        if not self._Session:
            return
        try:
            with self._Session() as session:
                log = APILog(
                    provider="riot",
                    endpoint=endpoint,
                    requesting_user=None,
                    args=dict(params or {}),
                    full_call=full_url,
                )
                session.add(log)
                session.commit()
        except Exception:
            # Do not break API flow on logging failures
            pass

    # removed: storing matches is now handled inside specific endpoint methods for clarity

    # ---------- League of Legends (LoL) endpoints ----------
    def lol_get_summoner_by_name(self, summoner_name: str) -> Mapping[str, Any]:
        url = f"{self._platform_base()}/lol/summoner/v4/summoners/by-name/{summoner_name}"
        data = self._get_json(url)
        self._log_api(endpoint="/lol/summoner/v4/summoners/by-name", params={"summoner_name": summoner_name}, full_url=str(httpx.URL(url)))
        # upsert into summoners
        if self._Session and isinstance(data, Mapping) and isinstance(data.get("puuid"), str):
            try:
                with self._Session() as session:
                    puuid = str(data["puuid"])  # type: ignore[index]
                    existing = session.get(Summoner, puuid)
                    values = {
                        "discord_id": None,
                        "profile_icon_id": data.get("profileIconId"),
                        "revision_date": data.get("revisionDate"),
                        "summoner_level": data.get("summonerLevel"),
                    }
                    if existing:
                        for k, v in values.items():
                            setattr(existing, k, v)
                    else:
                        session.add(Summoner(puuid=puuid, **values))
                    session.commit()
            except Exception:
                pass
        return data

    def lol_get_summoner_by_puuid(self, puuid: str) -> Mapping[str, Any]:
        # cache-first by PUUID
        if self._Session:
            try:
                with self._Session() as session:
                    cached = session.get(Summoner, puuid)
                    if cached:
                        return {
                            "puuid": cached.puuid,
                            "profileIconId": cached.profile_icon_id,
                            "revisionDate": cached.revision_date,
                            "summonerLevel": cached.summoner_level,
                        }
            except Exception:
                pass
        url = f"{self._platform_base()}/lol/summoner/v4/summoners/by-puuid/{puuid}"
        data = self._get_json(url)
        self._log_api(endpoint="/lol/summoner/v4/summoners/by-puuid", params={"puuid": puuid}, full_url=str(httpx.URL(url)))
        if self._Session and isinstance(data, Mapping) and isinstance(data.get("puuid"), str):
            try:
                with self._Session() as session:
                    puuid_val = str(data["puuid"])  # type: ignore[index]
                    existing = session.get(Summoner, puuid_val)
                    values = {
                        "discord_id": None,
                        "profile_icon_id": data.get("profileIconId"),
                        "revision_date": data.get("revisionDate"),
                        "summoner_level": data.get("summonerLevel"),
                    }
                    if existing:
                        for k, v in values.items():
                            setattr(existing, k, v)
                    else:
                        session.add(Summoner(puuid=puuid_val, **values))
                    session.commit()
            except Exception:
                pass
        return data

    def lol_get_league_entries_by_summoner(self, encrypted_summoner_id: str) -> List[Mapping[str, Any]]:
        url = f"{self._platform_base()}/lol/league/v4/entries/by-summoner/{encrypted_summoner_id}"
        data = self._get_json(url)
        self._log_api(endpoint="/lol/league/v4/entries/by-summoner", params={"summoner_id": encrypted_summoner_id}, full_url=str(httpx.URL(url)))
        return data

    def lol_get_status(self) -> Mapping[str, Any]:
        url = f"{self._platform_base()}/lol/status/v4/platform-data"
        data = self._get_json(url)
        self._log_api(endpoint="/lol/status/v4/platform-data", params=None, full_url=str(httpx.URL(url)))
        return data

    def lol_get_match_ids_by_puuid(self, puuid: str, start: int = 0, count: int = 20) -> List[str]:
        params = {"start": start, "count": count}
        url = f"{self._region_base()}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        data = self._get_json(url, params=params)
        self._log_api(endpoint="/lol/match/v5/matches/by-puuid/ids", params={"puuid": puuid, **params}, full_url=str(httpx.URL(url, params=params)))
        return data

    # ---------- Riot Accounts (cross-game) endpoints ----------
    def account_get_by_riot_id(self, game_name: str, tag_line: str) -> Mapping[str, Any]:
        """Lookup account by Riot ID (name + tagline) via regional account-v1 endpoint."""
        url = f"{self._region_base()}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        data = self._get_json(url)
        self._log_api(endpoint="/riot/account/v1/accounts/by-riot-id", params={"gameName": game_name, "tagLine": tag_line}, full_url=str(httpx.URL(url)))
        return data

    def account_get_by_puuid(self, puuid: str) -> Mapping[str, Any]:
        url = f"{self._region_base()}/riot/account/v1/accounts/by-puuid/{puuid}"
        data = self._get_json(url)
        self._log_api(endpoint="/riot/account/v1/accounts/by-puuid", params={"puuid": puuid}, full_url=str(httpx.URL(url)))
        return data

    def lol_get_match(self, match_id: str) -> Mapping[str, Any]:
        # cache-first by match id
        if self._Session:
            try:
                with self._Session() as session:
                    cached = session.get(LOLMatch, match_id)
                    if cached:
                        return cached.match_data
            except Exception:
                pass
        api_version = "v5"
        url = f"{self._region_base()}/lol/match/{api_version}/matches/{match_id}"
        data = self._get_json(url)
        self._log_api(endpoint=f"/lol/match/{api_version}/matches", params={"match_id": match_id}, full_url=str(httpx.URL(url)))
        # persist LoL match
        if self._Session and isinstance(data, Mapping):
            try:
                # populate "players" column with info.participants.puuid
                info = data.get("info") if isinstance(data.get("info"), Mapping) else {}
                participants = info.get("participants") if isinstance(info, Mapping) else None
                players: List[str] = []
                if isinstance(participants, list):
                    players = [str(p.get("puuid")) for p in participants if isinstance(p, Mapping) and p.get("puuid")]

                # populate into the table using super cool alembic
                with self._Session() as session:
                    existing = session.get(LOLMatch, match_id)
                    if existing:
                        existing.match_data = dict(data)
                        if players:
                            existing.players = players
                        if api_version:
                            existing.api_version = api_version
                    else:
                        session.add(LOLMatch(id=match_id, match_data=dict(data), players=players, api_version=api_version))
                    session.commit()
            except Exception:
                pass
        return data

    # ---------- Teamfight Tactics (TFT) endpoints ----------
    def tft_get_summoner_by_name(self, summoner_name: str) -> Mapping[str, Any]:
        url = f"{self._platform_base()}/tft/summoner/v1/summoners/by-name/{summoner_name}"
        data = self._get_json(url)
        self._log_api(endpoint="/tft/summoner/v1/summoners/by-name", params={"summoner_name": summoner_name}, full_url=str(httpx.URL(url)))
        if self._Session and isinstance(data, Mapping) and isinstance(data.get("puuid"), str):
            try:
                with self._Session() as session:
                    puuid = str(data["puuid"])  # type: ignore[index]
                    existing = session.get(Summoner, puuid)
                    values = {
                        "discord_id": None,
                        "profile_icon_id": data.get("profileIconId"),
                        "revision_date": data.get("revisionDate"),
                        "summoner_level": data.get("summonerLevel"),
                    }
                    if existing:
                        for k, v in values.items():
                            setattr(existing, k, v)
                    else:
                        session.add(Summoner(puuid=puuid, **values))
                    session.commit()
            except Exception:
                pass
        return data

    def tft_get_summoner_by_puuid(self, puuid: str) -> Mapping[str, Any]:
        # cache-first by PUUID
        if self._Session:
            try:
                with self._Session() as session:
                    cached = session.get(Summoner, puuid)
                    if cached:
                        return {
                            "puuid": cached.puuid,
                            "profileIconId": cached.profile_icon_id,
                            "revisionDate": cached.revision_date,
                            "summonerLevel": cached.summoner_level,
                        }
            except Exception:
                pass
        url = f"{self._platform_base()}/tft/summoner/v1/summoners/by-puuid/{puuid}"
        data = self._get_json(url)
        self._log_api(endpoint="/tft/summoner/v1/summoners/by-puuid", params={"puuid": puuid}, full_url=str(httpx.URL(url)))
        if self._Session and isinstance(data, Mapping) and isinstance(data.get("puuid"), str):
            try:
                with self._Session() as session:
                    puuid_val = str(data["puuid"])  # type: ignore[index]
                    existing = session.get(Summoner, puuid_val)
                    values = {
                        "discord_id": None,
                        "profile_icon_id": data.get("profileIconId"),
                        "revision_date": data.get("revisionDate"),
                        "summoner_level": data.get("summonerLevel"),
                    }
                    if existing:
                        for k, v in values.items():
                            setattr(existing, k, v)
                    else:
                        session.add(Summoner(puuid=puuid_val, **values))
                    session.commit()
            except Exception:
                pass
        return data

    def tft_get_league_entries_by_summoner(self, encrypted_summoner_id: str) -> List[Mapping[str, Any]]:
        url = f"{self._platform_base()}/tft/league/v1/entries/by-summoner/{encrypted_summoner_id}"
        data = self._get_json(url)
        self._log_api(endpoint="/tft/league/v1/entries/by-summoner", params={"summoner_id": encrypted_summoner_id}, full_url=str(httpx.URL(url)))
        return data

    def tft_get_status(self) -> Mapping[str, Any]:
        url = f"{self._platform_base()}/tft/status/v1/platform-data"
        data = self._get_json(url)
        self._log_api(endpoint="/tft/status/v1/platform-data", params=None, full_url=str(httpx.URL(url)))
        return data

    def tft_get_match_ids_by_puuid(self, puuid: str, start: int = 0, count: int = 20) -> List[str]:
        params = {"start": start, "count": count}
        url = f"{self._region_base()}/tft/match/v1/matches/by-puuid/{puuid}/ids"
        data = self._get_json(url, params=params)
        self._log_api(endpoint="/tft/match/v1/matches/by-puuid/ids", params={"puuid": puuid, **params}, full_url=str(httpx.URL(url, params=params)))
        return data

    def tft_get_match(self, match_id: str) -> Mapping[str, Any]:
        # cache-first by match id
        if self._Session:
            try:
                with self._Session() as session:
                    cached = session.get(TFTMatch, match_id)
                    if cached:
                        return cached.match_data
            except Exception:
                pass
        api_version = "v1"
        url = f"{self._region_base()}/tft/match/{api_version}/matches/{match_id}"
        data = self._get_json(url)
        self._log_api(endpoint=f"/tft/match/{api_version}/matches", params={"match_id": match_id}, full_url=str(httpx.URL(url)))
        # persist TFT match
        if self._Session and isinstance(data, Mapping):
            try:
                metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
                players: List[str] = []
                if isinstance(metadata, Mapping) and isinstance(metadata.get("participants"), list):
                    players = [str(p) for p in metadata.get("participants")]


                with self._Session() as session:
                    existing = session.get(TFTMatch, match_id)
                    if existing:
                        existing.match_data = dict(data)
                        if players:
                            existing.players = players
                        if api_version:
                            existing.api_version = api_version
                    else:
                        session.add(TFTMatch(id=match_id, match_data=dict(data), players=players, api_version=api_version))
                    session.commit()
            except Exception:
                pass
        return data


# ---------- Module-level convenience ----------
_default_client: RiotApiClient | None = None


def get_default_client() -> RiotApiClient:
    global _default_client
    if _default_client is None:
        _default_client = RiotApiClient(
            api_key=os.getenv("RIOT_API_KEY"),
            platform=os.getenv("RIOT_PLATFORM", "na1"),
            region=os.getenv("RIOT_REGION", "americas"),
        )
    return _default_client


__all__ = [
    "RiotApiClient",
    "RiotApiError"
]


