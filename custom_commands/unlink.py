from utils.postgres import RiotPostgresManager
from dotenv import load_dotenv
from discord.ext import commands

load_dotenv()

async def run(ctx):
    """
    Link your Discord account with your League of Legends account.
    Usage: !link <summoner_name#tag>
    Example: !link Doublelift#NA1
    """
    try:
        discord_name = ctx.message.author.name
        pg = RiotPostgresManager()
        pg.execute_query(f"delete from riot.summoners where discord_name = '{discord_name}'")

        await ctx.message.channel.send(f'Unlinked summoner account info for: {discord_name}')
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
