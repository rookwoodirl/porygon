import discord
from discord.ext import commands
from commands.chess_gif import pgn_to_gif
from commands.factorio_blueprint import BlueprintImageConstructor
import os
from openai import OpenAI
with open(os.path.join('api_keys', 'chatgpt.key'), 'r') as f:
    chat_client = OpenAI(api_key=f.readline())

# Replace 'YOUR_BOT_TOKEN' with your actual bot token
with open(os.path.join('api_keys', 'discord.key'), 'r') as f:
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


gpt_activated = False
gpt_pass_counter = 0

# Event handler for when a message is received
@bot.event
async def on_message(message):

    global gpt_activated
    global gpt_pass_counter

    # Ignore messages from the bot itself to prevent infinite loops
    if message.author == bot.user:
        return

    # Respond to a specific message content
    if message.content.lower() == 'ping':
        await message.channel.send('Pong!')

    # Process commands
    await bot.process_commands(message)

    if 'pory' in message.content.lower() or '<@270372309273023273 >' in message.content:
        gpt_activated = True

    if gpt_pass_counter >= 5:
        gpt_activated = False

    if gpt_activated and len(message.content) < 1000:
        # chatgpt
        gpt_channels = ['日本語', 'italiano', 'deutsch', '한국어', 'español', 'bot-spam']
        with open(os.path.join('assets', 'chatgpt', 'languages.prompt')) as f:
            prompt = [
                {
                    "role": "system", 
                    "content": '\n'.join(f.readlines())
                }
            ]
        if message.channel.name in gpt_channels:
            new_prompt = prompt.copy()
            messages = [msg async for msg in message.channel.history(limit=10)]
            for message in reversed(messages):
                new_prompt.append({"role": "assistant" if message.author.display_name == "Porygon" else "user", "content": message.content[:2000]})

            

            response = chat_client.chat.completions.create(model="gpt-4",  messages=new_prompt)
            reply = response.choices[0].message.content
            if reply.lower()[:4] != "pass":
                gpt_pass_counter = 0
                await message.channel.send(reply)
            else:
                gpt_pass_counter += 1

            if gpt_pass_counter == 5:
                await message.channel.send("Zzzzz...... so sleepy....")





# Start the bot
bot.run(BOT_TOKEN)