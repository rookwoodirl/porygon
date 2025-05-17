from utils.riot import MatchData, EmojiHandler
import discord
import os


CHANNEL_NAME = 'lol-match-history'
if os.environ.get('ENV', 'prod') == 'dev':
    CHANNEL_NAME += '-dev'


async def run(ctx):

    if not EmojiHandler._initialized:
        await EmojiHandler.initialize()

    if ctx.message.channel.name != CHANNEL_NAME:
        return

    match_id = ctx.message.content.replace('!match_summary ', '').strip()
    match = MatchData(match_id)
    await match.initialize()  # Make sure match data is loaded if needed



    embed = match.to_embed()
    await ctx.send(embed=embed)
    await ctx.message.delete()