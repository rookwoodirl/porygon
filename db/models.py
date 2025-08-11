from __future__ import annotations

from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Text, String, func, Identity, Numeric
from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(schema="porygon")
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=0, increment=1), primary_key=True)
    discord_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    discord_channel_id: Mapped[str] = mapped_column(Text, nullable=False)
    discord_message_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    author_id: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)



class Match:
    id: Mapped[str] = mapped_column(String(64), primary_key=True, nullable=False, unique=True)
    match_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    players: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    api_version: Mapped[str] = mapped_column(String(16), nullable=False)

class TFTMatch(Base, Match):
    __tablename__ = "matches_tft"
    pass

class LOLMatch(Base, Match):
    __tablename__ = "matches_lol"
    pass



class Summoner(Base):
    __tablename__ = "summoners"
    """SummonerDTO for both LoL and TFT (shared shape)."""
    puuid: Mapped[str] = mapped_column(String(78), primary_key=True, nullable=False, unique=True)
    discord_id: Mapped[str] = mapped_column(String(32), nullable=True)
    profile_icon_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    revision_date: Mapped[int] = mapped_column(BigInteger, nullable=True)
    summoner_level: Mapped[int] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Account(Base):
    __tablename__ = "accounts"
    """Links a Discord user id to a Riot PUUID. Composite primary key allows multiple links per user."""
    discord_id: Mapped[str] = mapped_column(String(32), primary_key=True, nullable=False)
    puuid: Mapped[str] = mapped_column(String(78), primary_key=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class APILog(Base):
    __tablename__ = "log_api"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=0, increment=1), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False)
    requesting_user: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    args: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    full_call: Mapped[str] = mapped_column(Text, nullable=False)


class Billing(Base):
    __tablename__ = "billing"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)
    context_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tools: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    tokens_input: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tokens_output: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    discord_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    discord_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


__all__ = [
    "Base",
    "User",
    "Message",
    "TFTMatch",
    "LOLMatch",
    "APILog",
    "Summoner",
    "Account",
    "Billing",
    "ModelPricing",
]


class ModelPricing(Base):
    __tablename__ = "model_pricing"

    model: Mapped[str] = mapped_column(String(128), primary_key=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usd_per_1k_tokens_input: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    usd_per_1k_tokens_output: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)

