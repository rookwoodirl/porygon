from __future__ import annotations

import asyncio
import discord
from discord.ext import commands

from util.embeds import embed_for_text
from util.accounts import link_puuid_to_discord
from util.riot import get_default_client, RiotApiError


def setup_basic_commands(bot: commands.Bot) -> None:
    @bot.command(name='ping')
    async def ping(ctx):
        latency = round(bot.latency * 1000)
        await ctx.send(embed=embed_for_text(f'Pong! Latency: {latency}ms'))

    @bot.command(name='hello')
    async def hello(ctx):
        await ctx.send(embed=embed_for_text(f'Hello {ctx.author.mention}! I am Porygon, your Discord bot!'))

    @bot.command(name='lollink')
    async def lollink(ctx):
        try:
            content = (ctx.message.content or "").strip()
            parts = content.split()
            if len(parts) < 2:
                await ctx.send(embed=embed_for_text("Usage: `!lollink RiotName#TAG`"))
                return
            riot_id = parts[1].strip()
            if "#" not in riot_id:
                await ctx.send(embed=embed_for_text("Please provide a Riot ID in the form `Name#TAG`."))
                return
            name, tag = riot_id.split("#", 1)
            client = get_default_client()
            try:
                acct = await asyncio.to_thread(client.account_get_by_riot_id, name, tag)
            except RiotApiError as e:
                await ctx.send(embed=embed_for_text(f"Riot API error: {e}"))
                return
            puuid = acct.get("puuid")
            if not puuid:
                await ctx.send(embed=embed_for_text("Could not find account PUUID for that Riot ID."))
                return
            ok = link_puuid_to_discord(puuid, discord_id=str(ctx.author.id))
            if ok:
                await ctx.send(embed=embed_for_text(f"Linked Riot account {name}#{tag} to {ctx.author.mention}."))
            else:
                await ctx.send(embed=embed_for_text("Failed to link account (database unavailable)."))
        except Exception as e:
            await ctx.send(embed=embed_for_text(f"Error linking account: {e}"))


__all__ = ["setup_basic_commands"]


