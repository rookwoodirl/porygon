from __future__ import annotations

from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Text, String, func, Identity
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

class APILog(Base):
    __tablename__ = "log_api"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=0, increment=1), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False)
    requesting_user: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    args: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    full_call: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = ["Base", "User", "Message", "TFTMatch", "LOLMatch", "APILog"]

