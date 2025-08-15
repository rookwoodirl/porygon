from __future__ import annotations

import asyncio
from discord.ext import commands
from util.embeds import embed_for_text


def setup_pokedle_commands(bot: commands.Bot) -> None:
    @bot.command(name='pokedle')
    async def pokedle(ctx):
        try:
            import importlib
            mod = importlib.import_module('games.pokedle')
        except Exception:
            await ctx.send(embed=embed_for_text("Pokedle game is not available on this bot."))
            return

        PokedleGame = getattr(mod, 'PokedleGame', None)
        if PokedleGame is None:
            await ctx.send(embed=embed_for_text("Pokedle module present but game class not found."))
            return

        try:
            starter = await ctx.send(f"{ctx.author.mention} is starting a Pokedle game... creating thread...")
            thread = await starter.create_thread(name=f"Pokedle — {ctx.author.display_name}", auto_archive_duration=60)
            bot_msg = await thread.send("Preparing game...")
            game = PokedleGame(bot, ctx.author)
            await game.setup(ctx)
            asyncio.create_task(game.run_in_thread(thread, bot_msg))
            await ctx.send(embed=embed_for_text(f"Pokedle started in thread {thread.mention}"))
        except Exception as e:
            await ctx.send(embed=embed_for_text(f"Failed to start Pokedle: {e}"))


__all__ = ["setup_pokedle_commands"]


