from utils.riot import MatchMessage, EmojiHandler
import asyncio
import os

class SimulatedReaction:
    def __init__(self, emoji):
        self.emoji = emoji


CHANNEL_NAME = 'lol-match-history'
if os.environ.get('ENV', 'prod') == 'dev':
    CHANNEL_NAME += '-dev'

async def run(ctx):
    if not EmojiHandler._initialized:
        await EmojiHandler.initialize()

    if ctx.message.channel.name != CHANNEL_NAME:
        return
    
    if ctx.message.reference:
        match = MatchMessage.MESSAGES.get(ctx.message.reference.resolved.id, None)

    if match:
        roles = ctx.message.content.upper().split(' ')
        for role in roles:
            if role in match.role_emojis:
                await match.on_react(SimulatedReaction(match.role_emojis[role]), ctx.message.author)
    
    await ctx.message.delete()