from utils.riot import MatchMessage, EmojiHandler
import asyncio

class SimulatedReaction:
    def __init__(self, emoji):
        self.emoji = emoji

async def run(ctx):
    if not EmojiHandler._initialized:
        await EmojiHandler.initialize()
    print(ctx.message.author)
    for match in MatchMessage.MESSAGES.values():
        if match.message.guild == ctx.message.guild and match.message.channel == ctx.message.channel and (ctx.message.author.name in match.players or ctx.message.author.name in match.queued_players):
            roles = match.player_preferences[ctx.message.author.name]
            for role in roles:
                await match.on_unreact(SimulatedReaction(match.role_emojis[role]), ctx.message.author)
    
    await ctx.message.delete()