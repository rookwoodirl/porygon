from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

import httpx


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

    def __post_init__(self) -> None:
        """This is called after __init__ and handles some simple setup."""
        if not self.api_key:
            self.api_key = os.getenv("RIOT_API_KEY")
        if not self.api_key:
            raise ValueError("RIOT_API_KEY not set. Provide api_key or set environment variable.")
        self.platform = _normalize_platform(self.platform)
        self.region = _normalize_region(self.region)
        self._client = httpx.Client(timeout=self.timeout_seconds)

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

    # ---------- League of Legends (LoL) endpoints ----------
    def lol_get_summoner_by_name(self, summoner_name: str) -> Mapping[str, Any]:
        url = f"{self._platform_base()}/lol/summoner/v4/summoners/by-name/{summoner_name}"
        return self._get_json(url)

    def lol_get_summoner_by_puuid(self, puuid: str) -> Mapping[str, Any]:
        url = f"{self._platform_base()}/lol/summoner/v4/summoners/by-puuid/{puuid}"
        return self._get_json(url)

    def lol_get_league_entries_by_summoner(self, encrypted_summoner_id: str) -> List[Mapping[str, Any]]:
        url = f"{self._platform_base()}/lol/league/v4/entries/by-summoner/{encrypted_summoner_id}"
        return self._get_json(url)

    def lol_get_status(self) -> Mapping[str, Any]:
        url = f"{self._platform_base()}/lol/status/v4/platform-data"
        return self._get_json(url)

    def lol_get_match_ids_by_puuid(self, puuid: str, start: int = 0, count: int = 20) -> List[str]:
        params = {"start": start, "count": count}
        url = f"{self._region_base()}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        return self._get_json(url, params=params)

    def lol_get_match(self, match_id: str) -> Mapping[str, Any]:
        url = f"{self._region_base()}/lol/match/v5/matches/{match_id}"
        return self._get_json(url)

    # ---------- Teamfight Tactics (TFT) endpoints ----------
    def tft_get_summoner_by_name(self, summoner_name: str) -> Mapping[str, Any]:
        url = f"{self._platform_base()}/tft/summoner/v1/summoners/by-name/{summoner_name}"
        return self._get_json(url)

    def tft_get_summoner_by_puuid(self, puuid: str) -> Mapping[str, Any]:
        url = f"{self._platform_base()}/tft/summoner/v1/summoners/by-puuid/{puuid}"
        return self._get_json(url)

    def tft_get_league_entries_by_summoner(self, encrypted_summoner_id: str) -> List[Mapping[str, Any]]:
        url = f"{self._platform_base()}/tft/league/v1/entries/by-summoner/{encrypted_summoner_id}"
        return self._get_json(url)

    def tft_get_status(self) -> Mapping[str, Any]:
        url = f"{self._platform_base()}/tft/status/v1/platform-data"
        return self._get_json(url)

    def tft_get_match_ids_by_puuid(self, puuid: str, start: int = 0, count: int = 20) -> List[str]:
        params = {"start": start, "count": count}
        url = f"{self._region_base()}/tft/match/v1/matches/by-puuid/{puuid}/ids"
        return self._get_json(url, params=params)

    def tft_get_match(self, match_id: str) -> Mapping[str, Any]:
        url = f"{self._region_base()}/tft/match/v1/matches/{match_id}"
        return self._get_json(url)


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


