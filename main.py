import discord
import os, sys
from discord.ext import commands

from tools import Tool
from chat import get_chatgpt_response
import importlib.util

from utils import riot



from dotenv import load_dotenv
load_dotenv()


# Create a client instance
intents = discord.Intents.default()
intents.message_content = True  # Needed to read mes
bot = commands.Bot(command_prefix="!", intents=intents)
riot.bot = bot




def say_hello():
    "Says hello!"
    return 'Hello, world!'

Tool(say_hello)



commands_dir = "custom_commands"



def load_commands():
    for filename in os.listdir(commands_dir):
        if filename.endswith(".py"):
            command_name = filename[:-3]  # Strip .py
            filepath = os.path.join(commands_dir, filename)

            # Dynamically import the module
            spec = importlib.util.spec_from_file_location(command_name, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Create command from the run() function
            def create_command(current_module):
                @bot.command(name=command_name)
                async def dynamic_command(ctx):
                    try:
                        current_module.bot = bot
                        output = await current_module.run(ctx)
                        if output is not None:  # Only send if there's an output
                            await ctx.send(str(output))
                    except Exception as e:
                        print(f"Error running `{command_name}`: {e}")
                        await ctx.send(f"Error running `{command_name}`: {e}")
                return dynamic_command

            # Create and register the command with the correct module
            create_command(module)
            print(f"Loaded command: {command_name}")

load_commands()


@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    await riot.EmojiHandler.initialize()

@bot.event
async def on_message(message):
    # Ignore the bot's own messages
    if message.author == bot.user:
        return
    elif message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return
    elif message.channel.category and message.channel.category.name in [
        'Languages',
        'bot-stuff'
    ]:
        response = await get_chatgpt_response(message.channel)
        await message.channel.send(response)
    else:
        return











if __name__ == '__main__':
    if '--deploy' in sys.argv:
        bot.run(os.environ['DISCORD_API_KEY'])


