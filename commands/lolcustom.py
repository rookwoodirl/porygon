from __future__ import annotations
from typing import Tuple
import os
import asyncio
import discord
from discord.ext import commands
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from util.embeds import embed_for_text
from util.lolcustom import LolCustomManager, ROLE_NAMES, plan_teams, PlayerChoice
from db.models import Account
from util.riot import get_default_client


def setup_lolcustom(bot: commands.Bot) -> None:
    manager = LolCustomManager()
    tracked_messages: set[int] = set()
    riot_client = get_default_client()
    _SessionFactory: sessionmaker | None = None
    emoji_map: dict[str, discord.Emoji] = {}

    def format_plan(plan) -> str:
        def line_for(team_map: dict, label: str, total_lp: int) -> list[str]:
            lines = [f"{label} (sum LP: {total_lp})"]
            for role in ROLE_NAMES:
                p = team_map.get(role)
                if not p:
                    lines.append(f"- {role}: <unassigned>")
                    continue
                mention = f"<@{p.discord_id}>"
                lines.append(f"- {role}: {mention} ({p.rating} LP)")
            return lines

        parts: list[str] = []
        parts.extend(line_for(plan.team_a, "Team A", plan.lp_team_a))
        parts.append("")
        parts.extend(line_for(plan.team_b, "Team B", plan.lp_team_b))
        parts.append("")
        parts.append(f"LP diff: {plan.lp_diff}")
        if getattr(plan, "penalty_total", 0):
            parts.append(f"Note: {plan.penalty_total} role preference violation(s) to make teams valid.")
        return "\n".join(parts)

    async def add_role_reactions(message: discord.Message) -> None:
        nonlocal emoji_map
        emoji_map = { emoji.name.upper() : emoji for emoji in await bot.fetch_application_emojis() }
        def resolve(name_upper: str) -> discord.Emoji | None:
            return emoji_map.get(name_upper)
        for role in ROLE_NAMES:
            try:
                pe = resolve(role)
                if pe is not None:
                    await message.add_reaction(pe)
                else:
                    await message.add_reaction(role)
            except Exception:
                continue

    def _get_session_factory() -> sessionmaker | None:
        nonlocal _SessionFactory
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

    async def _resolve_riot_display(discord_id: str, rating: int) -> str:
        sf = _get_session_factory()
        if not sf:
            return f"{discord_id} ({rating} LP)"
        puuid: str | None = None
        try:
            with sf() as s:
                row = s.execute(select(Account.puuid).where(Account.discord_id == str(discord_id))).first()
                puuid = row[0] if row else None
        except Exception:
            puuid = None
        if not puuid:
            return f"{discord_id} ({rating} LP)"
        try:
            acct = await asyncio.to_thread(riot_client.account_get_by_puuid, puuid)
            game_name = acct.get("gameName") or "?"
            tag_line = acct.get("tagLine") or "?"
            return f"{game_name}#{tag_line} ({rating} LP)"
        except Exception:
            return f"{discord_id} ({rating} LP)"

    async def build_wait_embed(status: dict) -> discord.Embed:
        count = int(status.get('count', 0) or 0)
        rows: list[Tuple[str, str, str]] = []
        try:
            for p in status.get("players", []) or []:
                did = str(p.get("discord_id") or "")
                rating = p.get("rating", 1400)
                # Roles as application emojis
                role_names = list(p.get("roles", []))
                role_emojis: list[str] = []
                for rn in role_names:
                    e = emoji_map.get(str(rn).upper())
                    role_emojis.append(str(e) if e else str(rn))
                roles_col = "".join(role_emojis) if role_emojis else "—"
                disp = await _resolve_riot_display(did, rating)
                rows.append((f"<@{did}>", disp, roles_col))
        except Exception:
            pass

        col1 = "\n".join(r[0] for r in rows) or "—"
        col2 = "\n".join(r[1] for r in rows) or "—"
        col3 = "\n".join(r[2] for r in rows) or "—"

        emb = discord.Embed(description=f"Players: {count}/10", title="LoL Custom Queue", color=0x2F3136)
        emb.add_field(name="Discord", value=col1, inline=True)
        emb.add_field(name="Riot ID (LP)", value=col2, inline=True)
        emb.add_field(name="Roles", value=col3, inline=True)
        return emb

    async def update_message(channel_id: int, message_id: int, plan_or_none) -> None:
        try:
            ch = bot.get_channel(int(channel_id)) or await bot.fetch_channel(int(channel_id))
            msg = await ch.fetch_message(int(message_id))
        except Exception:
            return
        try:
            if plan_or_none is None:
                status = manager.status(str(message_id))
                embed = await build_wait_embed(status)
                await msg.edit(embed=embed)
            else:
                text = format_plan(plan_or_none)
                await msg.edit(embed=embed_for_text(text, title="LoL Custom — Teams"))
                try:
                    tracked_messages.discard(int(message_id))
                    manager.clear(str(message_id))
                except Exception:
                    pass
        except Exception:
            return

    @bot.command(name='lolcustom')
    async def lolcustom(ctx):
        try:
            desc = (
                "React with your preferred roles: TOP, JGL, MID, BOT, SUP.\n"
                "You can pick multiple. The first 10 players will be placed into two balanced teams.\n"
                "Default rating is 1400 LP if no Riot account is linked."
            )
            starter = await ctx.send(embed=embed_for_text(desc, title="LoL Custom Queue"))
            tracked_messages.add(starter.id)
            await add_role_reactions(starter)
        except Exception as e:
            await ctx.send(embed=embed_for_text(f"Failed to start lolcustom: {e}"))

    @bot.command(name='lolcustom_test')
    async def lolcustom_test(ctx):
        role_list = [
            "TOP", "JGL", "MID", "BOT", "SUP",
            "TOP", "JGL", "MID", "BOT", "SUP",
        ]
        spoof_players = [
            PlayerChoice(discord_id=f"spoof{i}", roles={role}, rating=1200 + i*40) for i, role in enumerate(role_list)
        ]
        plan = plan_teams(spoof_players)
        text = format_plan(plan) if plan else "Could not balance test teams."
        await ctx.send(embed=embed_for_text(text, title="Lolcustom Test Plan"))

    @bot.event
    async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
        if int(getattr(payload, 'message_id', 0)) not in tracked_messages:
            return
        try:
            if bot.user and int(payload.user_id) == int(bot.user.id):
                return
        except Exception:
            pass
        emoji_name = getattr(getattr(payload, 'emoji', None), 'name', None) or ''
        plan = manager.register_reaction(str(payload.message_id), str(payload.user_id), emoji_name, True)
        await update_message(int(payload.channel_id), int(payload.message_id), plan)

    @bot.event
    async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
        if int(getattr(payload, 'message_id', 0)) not in tracked_messages:
            return
        emoji_name = getattr(getattr(payload, 'emoji', None), 'name', None) or ''
        plan = manager.register_reaction(str(payload.message_id), str(payload.user_id), emoji_name, False)
        await update_message(int(payload.channel_id), int(payload.message_id), plan)


__all__ = ["setup_lolcustom"]


