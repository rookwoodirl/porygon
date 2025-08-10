import os
import asyncio
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI
from context import get_context

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production').lower()
TOKEN_ENV_VAR = 'DISCORD_TOKEN_DEV' if ENVIRONMENT == 'development' else 'DISCORD_TOKEN'
TOKEN = os.getenv(TOKEN_ENV_VAR)
PREFIX = os.getenv('COMMAND_PREFIX', '!')
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

# OpenAI configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4.5')
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

if DEBUG:
    logging.getLogger().setLevel(logging.DEBUG)

# Define intents (admin-level: enable all, including privileged)
intents = discord.Intents.all()
intents.message_content = True  # Ensure message content is enabled for prefix commands

# Create bot instance
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    """Event triggered when the bot is ready and connected to Discord."""
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is in {len(bot.guilds)} guilds')

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"Command not found. Use `{PREFIX}help` to see available commands.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument. Use `{PREFIX}help {ctx.command}` for usage.")
    else:
        logger.error(f"An error occurred: {error}")
        await ctx.send("An error occurred while processing the command.")

@bot.command(name='ping')
async def ping(ctx):
    """Simple ping command to test bot responsiveness."""
    latency = round(bot.latency * 1000)
    await ctx.send(f'Pong! Latency: {latency}ms')

@bot.command(name='hello')
async def hello(ctx):
    """Say hello to the user."""
    await ctx.send(f'Hello {ctx.author.mention}! I am Porygon, your Discord bot!')


async def _generate_openai_reply(context_lines: list[str], user_message: str, channel_name: str | None) -> str:
    """Call OpenAI to generate a reply using provided context."""
    if not openai_client:
        return "OpenAI API key is not configured. Please set OPENAI_API_KEY."

    # Fetch per-channel context (prompt and optional tools)
    ctx = get_context(channel_name or "")
    system_prompt = ctx.prompt

    # Build a compact context block
    context_block = "\n".join(f"- {line}" for line in context_lines)

    user_prompt = (
        "Recent context (last 10 messages, first 200 chars each):\n"
        f"{context_block}\n\n"
        "User just said:\n"
        f"{user_message}\n\n"
        "Respond appropriately."
    )

    def _call_openai():
        kwargs = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 400,
        }
        # Optionally enable tools if provided by channel context
        if getattr(ctx, "tools", None):
            kwargs["tools"] = ctx.tools  # type: ignore[assignment]
            kwargs["tool_choice"] = "auto"
        resp = openai_client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content.strip() if resp.choices else ""

    try:
        return await asyncio.to_thread(_call_openai)
    except Exception as e:  # pragma: no cover
        logger.error(f"OpenAI error: {e}")
        return "Sorry, I couldn't generate a response right now."


@bot.event
async def on_message(message: discord.Message):
    """Respond to each user message using OpenAI with recent context."""
    # Avoid responding to ourselves or other bots
    if message.author == bot.user or getattr(message.author, "bot", False):
        return

    # Collect previous 9 messages (first 200 chars) to pair with current = total 10
    context_lines: list[str] = []
    try:
        async for msg in message.channel.history(limit=9):
            if msg.id == message.id:
                continue
            author_name = getattr(msg.author, 'display_name', None) or msg.author.name
            content = (msg.content or "").replace("\n", " ")[:200]
            if content:
                context_lines.append(f"{author_name}: {content}")
    except Exception as e:  # pragma: no cover
        logger.debug(f"Could not fetch history for context: {e}")

    # Prepend the latest message content to ensure it's included
    latest_author = getattr(message.author, 'display_name', None) or message.author.name
    latest_content = (message.content or "").replace("\n", " ")[:200]
    if latest_content:
        context_lines.insert(0, f"{latest_author}: {latest_content}")

    # Channel name best-effort (DMs may not have a name)
    try:
        channel_name = getattr(message.channel, "name", None)
    except Exception:
        channel_name = None

    # Generate and send reply
    reply_text = await _generate_openai_reply(context_lines, message.content or "", channel_name)
    if reply_text:
        try:
            await message.reply(reply_text)
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to send reply: {e}")

    # Ensure commands still work
    await bot.process_commands(message)

def main():
    """Main function to run the Discord bot."""
    if not TOKEN:
        logger.error(f"{TOKEN_ENV_VAR} not found in environment variables.")
        logger.error("Please create a .env file with your Discord bot token(s).")
        logger.error("You can use .env.example as a template. Set ENVIRONMENT=development to use DISCORD_TOKEN_DEV.")
        return
    
    try:
        logger.info("Starting Porygon Discord bot...")
        logger.info(f"Environment: {ENVIRONMENT} (using {TOKEN_ENV_VAR})")
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.error(f"Invalid Discord token. Please check your {TOKEN_ENV_VAR} in .env file.")
    except Exception as e:
        logger.error(f"An error occurred while running the bot: {e}")

if __name__ == "__main__":
    main()
