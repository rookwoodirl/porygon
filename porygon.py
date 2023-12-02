import discord
from discord.ext import commands
from commands.chess_gif import pgn_to_gif
from commands.factorio_blueprint import BlueprintImageConstructor
import os

# Replace 'YOUR_BOT_TOKEN' with your actual bot token
with open('discord.key', 'r') as f:
    BOT_TOKEN = f.readline().strip()

def log(command, text):
    with open('commands.log', 'a') as f:
        f.write(command, '|', text)

# Create a bot instance with a command prefix
intents = discord.Intents.all() 
#intents.messages = True
#intents.message_content = True
bot = commands.Bot(intents=intents, command_prefix='!')

# Event handler for when the bot is ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')

# Command to respond to a user's message
@bot.command(name='hello', help='Responds with a hello message')
async def hello(ctx):
    await ctx.send(f'Hello, {ctx.author.mention}!')

@bot.command(name='chess', help='Posts a gif given a PGN')
async def chess_gif(ctx, *pgn):
    try:
        with open('chess.pgn', 'w+') as f:
            f.write(' '.join(pgn))
        pgn_to_gif('chess.pgn', 'chess.gif')
        await ctx.send(file=discord.File('chess.gif'))
        # clean up after
        os.remove('chess.pgn')
        os.remove('chess.gif')
    except:
        await ctx.send("Looks like there was something wrong with that PGN you posted... fix it and try again!")
        log('chess', 'not a pgn: {}'.format(' '.join(pgn)))

@bot.command(name='fbp', help='Post a factorio blueprint and receive an image of the blueprint (WIP)')
async def fbp(ctx, *blueprint):
    with open('commands/factorio.bp', 'w+') as f:
        f.write(' '.join(blueprint))
    imgs = BlueprintImageConstructor('commands/factorio.bp', 'assets').get_image_files()
    for img in imgs:
        await ctx.send(file=discord.File(os.path.join('commands', img)))

# Event handler for when a message is received
@bot.event
async def on_message(message):
    # Ignore messages from the bot itself to prevent infinite loops
    if message.author == bot.user:
        return

    # Respond to a specific message content
    if message.content.lower() == 'ping':
        await message.channel.send('Pong!')

    # Process commands
    await bot.process_commands(message)


# Start the bot
bot.run(BOT_TOKEN)