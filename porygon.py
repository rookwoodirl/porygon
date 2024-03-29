import discord
from discord.ext import commands
from commands.chess_gif import pgn_to_gif
from commands.factorio_blueprint import BlueprintImageConstructor
import os
from openai import OpenAI

def get_secret(secret):
    if secret in os.environ:
        return os.environ[secret]
    else:
        with open(os.path.join('api_keys', f'{secret}.key'), 'r') as f:
            return f.readline().strip()
        
chat_client = OpenAI(api_key=get_secret('chatgpt'))

website = 'https://porygon-yhi5j.ondigitalocean.app'

from datetime import datetime

# Replace 'YOUR_BOT_TOKEN' with your actual bot token
BOT_TOKEN = get_secret('discord')

def log(command, text):
    with open('commands.log', 'a') as f:
        f.write('\n' + str(datetime.now()) + '|' + command + '|' + text)

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

@bot.command(name='flashcards', help='!flashcards <name> and then attach a .csv to your message with pairs of words to turn into flashcards!')
async def chess_gif(ctx, *args):
    file = ctx.message.attachments[0]
    name = args[0] + '.csv'
    await file.save(os.path.join('assets', 'flashcards', name))
    await ctx.send(f'You can quiz yourself at: {website}/flashcards/{args[0]}')

@bot.command(name='story', help='!story <word_list> <language> and pory will tell you a story using using your words so you can practice reading comprehension')
async def story(ctx, *args):

    with open(os.path.join('assets', 'flashcards', f'{args[0]}.csv'), 'r') as f:
        words = '\n'.join([j.split(',')[0] for j in f.readlines()])
    language = args[1]
    with open(os.path.join('assets', 'chatgpt', 'story.prompt')) as f:
        prompt = [
            {
                "role": "system", 
                "content": '\n'.join(f.readlines())
            }
        ]
    new_prompt = prompt.copy()
    messages = [f"""Pory, tell me a story that's <200 words (and <2000 characters) in {language} using these words:
                {words}
                If you need more words, type 1/X at the end of your story, 
                where X is how many messages you think you'll need. Your partner will say 'continue' to allow you to 
                continue your story."""]
    for message in reversed(messages):
        new_prompt.append({"role": "user", "content": messages[0]})

    response = chat_client.chat.completions.create(model="gpt-4",  messages=new_prompt)
    reply = response.choices[0].message.content
    await ctx.message.channel.send(reply[:2000])

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

    if 'pory' in message.content.lower() or '<@270372309273023273>' in message.content:
        gpt_activated = True
        gpt_pass_counter = 0

    if gpt_pass_counter >= 5:
        gpt_activated = False

    if gpt_activated and len(message.content) < 1000 and message.content[0] != '!':
        # chatgpt
        gpt_channels = ['日本語', 'italiano', 'deutsch', '한국어', 'español', 'norsk', 'bot-spam', 'dev-bot-spam']
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
                replies = [reply[i*2000:(i+1)*2000] for i in range(0, 1 + len(reply) // 2000)]
                for r in replies:
                    await message.channel.send(r)

                
            
            else:
                gpt_pass_counter += 1

            if gpt_pass_counter == 5:
                await message.channel.send("Zzzzz...... so sleepy....")







# role reacts
@bot.event
async def on_raw_reaction_add(payload):

    guild_id = payload.guild_id
    guild = discord.utils.find(lambda g: g.id == guild_id, bot.guilds)

    roles_dict = {
        '🥳' : 'Party Games'
    }

    # Replace with your guild ID, message ID, emoji, and role name
    if payload.channel_id == 1181995251594965142: # roles channel
        print(payload.emoji.name)
        if payload.emoji.name in roles_dict:
            role = discord.utils.get(guild.roles, name=roles_dict[payload.emoji.name])
        else:
            role = discord.utils.get(guild.roles, name=payload.emoji.name[0].upper() + payload.emoji.name[1:])
        if role:
            member = guild.get_member(payload.user_id)
            await member.add_roles(role)
            print(f"Added role {role.name} to {member.display_name}")
            log('roles', f"Added role {role.name} to {member.display_name}")




# Start the bot
try:
    bot.run(BOT_TOKEN)
except Exception as e:
    with open('errors.log', 'a') as f:
        f.write('------------------------------\n' + str(e) + '\n\n\n')