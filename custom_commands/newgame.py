from utils.riot import MatchMessage, SummonerProfile, EmojiHandler
import random
import os
import traceback
import sys
import discord

CHANNEL_NAME = 'lol-queue-pory'
if os.environ.get('ENV', 'prod') == 'dev':
    CHANNEL_NAME += '-dev'

async def run(ctx):

    if not EmojiHandler._initialized:
        await EmojiHandler.initialize()

    if ctx.channel.name != CHANNEL_NAME:
        return
    
    async for message in ctx.channel.history(limit=None):
        if message.id == ctx.message.id:
            continue
        if message.author == ctx.bot.user or message.content[0] == '!':
            try:
                await message.delete()
            except discord.NotFound:
                continue  # Message was already deleted
            except discord.Forbidden:
                print(f"Missing permissions to delete message {message.id}")
                continue
            except Exception as e:
                print(f"Error deleting message {message.id}: {e}")
                continue

    try:

        m = MatchMessage(ctx.message)
        await m.initialize()

        if os.environ.get('ENV', 'prod') == 'dev':
            # await simulate_users(m)
            pass

    except Exception as e:
        print("Error in run:", file=sys.stderr)
        print("Error type:", type(e).__name__, file=sys.stderr)
        print("Error message:", str(e), file=sys.stderr)
        print("Stack trace:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise


class SimulatedReaction:
    def __init__(self, emoji):
        self.emoji = emoji

async def simulate_users(match):
    """Simulate 9 users with hardcoded preferences."""
    # Each tuple: (username, [roles])
    role_emotes = await EmojiHandler.role_emojis()
    user_data = [
        ("User0",  random.sample(list(role_emotes.values()), 3)),
        ("User1",  random.sample(list(role_emotes.values()), 3)),
        ("User2",  random.sample(list(role_emotes.values()), 3)),
        ("User3",  random.sample(list(role_emotes.values()), 3)),
        ("User4",  random.sample(list(role_emotes.values()), 3)),
        ("User5",  random.sample(list(role_emotes.values()), 3)),
        ("User6",  random.sample(list(role_emotes.values()), 3)),
        ("User7",  random.sample(list(role_emotes.values()), 3)),
        ("User8",  random.sample(list(role_emotes.values()), 3)),
    ]
    
    # Directly update the data structures
    for user_name, roles in user_data:
        for role in roles:
            if len(match.players) < 10:
                profile = SummonerProfile(user_name, spoof=True)
                await profile.initialize()
                match.players[user_name] = profile
                match.player_preferences[user_name] = [role.name for role in roles]
            else:
                await match.on_react(SimulatedReaction(role), user_name)
            # await match.on_react(SimulatedReaction(role), user_name)
        
        print(f"Simulated {user_name} with roles: {[role.name for role in roles]}")
    
    await match.update_message()
