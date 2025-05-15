from utils.riot import MatchData
import discord

async def run(ctx):
    match_id = ctx.message.content.replace('!match_summary ', '').strip()
    match = MatchData(match_id)
    await match.initialize()  # Make sure match data is loaded if needed



    embed = await match.to_embed()
    await ctx.send(embed=embed)
    await ctx.message.delete()