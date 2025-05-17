from utils.riot import MatchData, EmojiHandler, SummonerProfile
import discord

async def run(ctx):

    if not EmojiHandler._initialized:
        await EmojiHandler.initialize()

    player = SummonerProfile(str(ctx.message.author))
    await player.initialize()


    matches = [MatchData(match_id) for match_id in await player.match_history()]

    for match in matches:
        await match.initialize()
        await ctx.channel.send(embed=match.to_embed())

    await ctx.message.delete()