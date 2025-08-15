from __future__ import annotations

import itertools
import os
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from db.models import Account
from util.riot import RiotApiClient, get_default_client


ROLE_NAMES: Tuple[str, ...] = ("TOP", "JGL", "MID", "BOT", "SUP")


def _now_ts() -> float:
    return time.time()


def _normalize_role(name: str) -> Optional[str]:
    if not name:
        return None
    key = name.strip().upper()
    if key in ROLE_NAMES:
        return key
    return None


def _get_session_factory() -> Optional[sessionmaker]:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return None
    try:
        engine = create_engine(dsn, future=True)
        return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    except Exception:
        return None


def _fetch_discord_puuids(discord_id: str) -> List[str]:
    sf = _get_session_factory()
    if not sf:
        return []
    try:
        with sf() as s:
            stmt = select(Account.puuid).where(Account.discord_id == str(discord_id))
            rows = s.execute(stmt).all()
            return [r[0] for r in rows]
    except Exception:
        return []


def _tier_to_base_rating(tier: str, division: Optional[str], lp: int) -> int:
    tier = (tier or "").upper()
    division = (division or "").upper() if division else None
    # Approximate continuous LP from Tier/Division/LP.
    tier_bases: Mapping[str, int] = {
        "IRON": 0,
        "BRONZE": 400,
        "SILVER": 800,
        "GOLD": 1200,
        "PLATINUM": 1600,
        "EMERALD": 2000,
        "DIAMOND": 2400,
        "MASTER": 2800,
        "GRANDMASTER": 3200,
        "CHALLENGER": 3600,
    }
    div_add: Mapping[str, int] = {
        "IV": 0,
        "III": 100,
        "II": 200,
        "I": 300,
    }
    base = tier_bases.get(tier, 1400)
    if tier in ("MASTER", "GRANDMASTER", "CHALLENGER"):
        return base + int(lp or 0)
    return base + div_add.get(division or "IV", 0) + int(lp or 0)


def _get_player_rating_from_riot(discord_id: str, *, client: Optional[RiotApiClient] = None) -> int:
    puuids = _fetch_discord_puuids(str(discord_id))
    if not puuids:
        return 1400
    client = client or get_default_client()
    try:
        # Pick most recent link (last)
        puuid = puuids[-1]
        summ = client.lol_get_summoner_by_puuid(puuid)
        enc_id = summ.get("id")
        if not enc_id:
            return 1400
        entries = client.lol_get_league_entries_by_summoner(enc_id)
        # Prefer SoloQ, fallback to Flex
        solo = next((e for e in entries if e.get("queueType") == "RANKED_SOLO_5x5"), None)
        target = solo or next((e for e in entries if e.get("queueType") == "RANKED_FLEX_SR"), None)
        if not target:
            return 1400
        return _tier_to_base_rating(target.get("tier", ""), target.get("rank"), int(target.get("leaguePoints", 0)))
    except Exception:
        return 1400


@dataclass
class PlayerChoice:
    discord_id: str
    roles: Set[str]
    rating: int


def _role_assignment_strict(players: Sequence[PlayerChoice]) -> Optional[Dict[str, PlayerChoice]]:
    # Backtracking assign roles with preference constraint
    role_to_candidates: Dict[str, List[PlayerChoice]] = {r: [] for r in ROLE_NAMES}
    for p in players:
        for r in ROLE_NAMES:
            if r in p.roles:
                role_to_candidates[r].append(p)
    # Order roles by scarcity of candidates
    roles_order = sorted(ROLE_NAMES, key=lambda r: len(role_to_candidates[r]))
    assignment: Dict[str, PlayerChoice] = {}
    used: Set[str] = set()

    def dfs(idx: int) -> bool:
        if idx == len(roles_order):
            return True
        role = roles_order[idx]
        for p in role_to_candidates[role]:
            if p.discord_id in used:
                continue
            used.add(p.discord_id)
            assignment[role] = p
            if dfs(idx + 1):
                return True
            used.remove(p.discord_id)
            assignment.pop(role, None)
        return False

    return assignment if dfs(0) else None


def _role_assignment_relaxed(players: Sequence[PlayerChoice]) -> Tuple[Dict[str, PlayerChoice], int]:
    # Try all permutations: map roles -> player ordering; minimize violations
    best: Optional[Tuple[Dict[str, PlayerChoice], int]] = None
    for perm in itertools.permutations(players, 5):
        penalty = 0
        mapping: Dict[str, PlayerChoice] = {}
        ok = True
        for role, player in zip(ROLE_NAMES, perm):
            if role not in player.roles:
                penalty += 1
            mapping[role] = player
        if not ok:
            continue
        if best is None or penalty < best[1]:
            best = (mapping, penalty)
            if penalty == 0:
                break
    if best is None:
        # Fallback arbitrary mapping
        mapping = {r: players[i] for i, r in enumerate(ROLE_NAMES)}
        return mapping, 5
    return best


def _sum_rating(players: Iterable[PlayerChoice]) -> int:
    return sum(p.rating for p in players)


@dataclass
class TeamPlan:
    team_a: Dict[str, PlayerChoice]
    team_b: Dict[str, PlayerChoice]
    lp_team_a: int
    lp_team_b: int
    lp_diff: int
    penalty_total: int


def plan_teams(players: Sequence[PlayerChoice]) -> Optional[TeamPlan]:
    if len(players) != 10:
        return None
    total_lp = _sum_rating(players)
    best_plan: Optional[TeamPlan] = None

    # Consider all 5-of-10 splits, ordered by LP diff
    comb_indices = list(itertools.combinations(range(10), 5))
    def split_lp_diff(idxs: Tuple[int, ...]) -> int:
        sum_a = sum(players[i].rating for i in idxs)
        sum_b = total_lp - sum_a
        return abs(sum_a - sum_b)
    comb_indices.sort(key=split_lp_diff)

    for idxs in comb_indices:
        team_a_players = [players[i] for i in idxs]
        team_b_players = [players[i] for i in range(10) if i not in idxs]
        # First try strict assignments
        a_assign = _role_assignment_strict(team_a_players)
        b_assign = _role_assignment_strict(team_b_players)
        penalty = 0
        if a_assign is None or b_assign is None:
            # Relaxed with penalty
            a_assign_relaxed, a_pen = _role_assignment_relaxed(team_a_players)
            b_assign_relaxed, b_pen = _role_assignment_relaxed(team_b_players)
            penalty = a_pen + b_pen
            a_assign = a_assign_relaxed
            b_assign = b_assign_relaxed
        lp_a = _sum_rating(a_assign.values())
        lp_b = _sum_rating(b_assign.values())
        diff = abs(lp_a - lp_b)
        candidate = TeamPlan(team_a=a_assign, team_b=b_assign, lp_team_a=lp_a, lp_team_b=lp_b, lp_diff=diff, penalty_total=penalty)
        if best_plan is None:
            best_plan = candidate
        else:
            if candidate.penalty_total < best_plan.penalty_total or (
                candidate.penalty_total == best_plan.penalty_total and candidate.lp_diff < best_plan.lp_diff
            ):
                best_plan = candidate
        if best_plan and best_plan.penalty_total == 0 and best_plan.lp_diff == 0:
            break
    return best_plan


@dataclass
class PlayerVote:
    discord_id: str
    roles: Set[str]
    joined_at: float
    rating_cache: Optional[int] = None


class LolCustomQueue:
    def __init__(self, *, riot_client: Optional[RiotApiClient] = None) -> None:
        self._votes: Dict[str, PlayerVote] = {}
        self._riot_client = riot_client

    def register_reaction(self, discord_id: str, emoji_name: str, added: bool) -> None:
        role = _normalize_role(emoji_name)
        if not role:
            return
        vote = self._votes.get(discord_id)
        if vote is None:
            if not added:
                return
            vote = PlayerVote(discord_id=str(discord_id), roles=set(), joined_at=_now_ts())
            self._votes[discord_id] = vote
        if added:
            vote.roles.add(role)
        else:
            vote.roles.discard(role)
            if not vote.roles:
                # Remove from queue if no roles selected
                self._votes.pop(discord_id, None)

    def _active_votes(self) -> List[PlayerVote]:
        # First 10 by join time with at least one role
        filtered = [v for v in self._votes.values() if v.roles]
        filtered.sort(key=lambda v: v.joined_at)
        return filtered[:10]

    def is_ready(self) -> bool:
        return len(self._active_votes()) == 10

    def _ensure_ratings(self, votes: Sequence[PlayerVote]) -> None:
        for v in votes:
            if v.rating_cache is None:
                v.rating_cache = _get_player_rating_from_riot(v.discord_id, client=self._riot_client)

    def try_make_teams(self) -> Optional[TeamPlan]:
        active = self._active_votes()
        if len(active) != 10:
            return None
        self._ensure_ratings(active)
        players = [PlayerChoice(discord_id=v.discord_id, roles=set(v.roles), rating=int(v.rating_cache or 1400)) for v in active]
        return plan_teams(players)

    def clear(self) -> None:
        self._votes.clear()

    def status(self) -> Dict[str, object]:
        active = self._active_votes()
        # Ensure ratings are present for display
        try:
            self._ensure_ratings(active)
        except Exception:
            pass
        return {
            "count": len(active),
            "players": [
                {
                    "discord_id": v.discord_id,
                    "roles": sorted(v.roles),
                    "rating": int(v.rating_cache or 1400),
                }
                for v in active
            ],
        }


class LolCustomManager:
    def __init__(self, *, riot_client: Optional[RiotApiClient] = None) -> None:
        self._queues: Dict[str, LolCustomQueue] = {}
        self._riot_client = riot_client or get_default_client()

    def _get_queue(self, message_id: str) -> LolCustomQueue:
        q = self._queues.get(str(message_id))
        if q is None:
            q = LolCustomQueue(riot_client=self._riot_client)
            self._queues[str(message_id)] = q
        return q

    def register_reaction(self, message_id: str, discord_id: str, emoji_name: str, added: bool) -> Optional[TeamPlan]:
        q = self._get_queue(message_id)
        q.register_reaction(discord_id, emoji_name, added)
        return q.try_make_teams()

    def status(self, message_id: str) -> Dict[str, object]:
        return self._get_queue(message_id).status()

    def clear(self, message_id: str) -> None:
        self._queues.pop(str(message_id), None)


__all__ = [
    "LolCustomQueue",
    "LolCustomManager",
    "plan_teams",
    "ROLE_NAMES",
]

