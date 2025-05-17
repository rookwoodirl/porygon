from utils.riot import MatchData, EmojiHandler, SummonerProfile
import discord

async def run(ctx):

    if not EmojiHandler._initialized:
        await EmojiHandler.initialize()
