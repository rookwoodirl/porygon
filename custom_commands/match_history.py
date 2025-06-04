from utils.riot import EmojiHandler, SummonerProfile
import discord
import os


CHANNEL_NAME = 'lol-match-history'
if os.environ.get('ENV', 'prod') == 'dev':
    CHANNEL_NAME += '-dev'


async def run(ctx):
    return
    