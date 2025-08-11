import os
import asyncio
import json
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI
from context import (
    get_context_by_name,
    get_context_options,
    get_default_context,
)
from tools import TOOL_REGISTRY

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
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
ROUTER_MODEL = os.getenv('ROUTER_MODEL', 'gpt-4o-mini')

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


def _route_context_name(user_message: str) -> str | None:
    """Use a small model to pick a context name from the registry. Returns None for default."""
    options = get_context_options()
    if not options or not openai_client:
        return None

    option_block = "\n".join(f"- {opt['name']}: {opt['doc']}" for opt in options)
    sys_msg = (
        "You are a context router. Choose the single best context name from the list based on the user's message.\n"
        "If none clearly apply, output 'default'.\n"
        "Output ONLY the name with no extra words."
    )
    user_msg = (
        f"Contexts:\n{option_block}\n\n"
        f"User message:\n{user_message}\n\n"
        "Answer with just the context name."
    )

    try:
        resp = openai_client.chat.completions.create(
            model=ROUTER_MODEL,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=8,
        )
        name = (resp.choices[0].message.content or "").strip()
        if name.lower() == 'default' or not name:
            return None
        # ensure it exists
        existing = {opt['name'] for opt in options}
        return name if name in existing else None
    except Exception:
        return None


async def _generate_openai_reply(context_lines: list[str], user_message: str, channel_name: str | None) -> str:
    """Call OpenAI to generate a reply using provided context."""
    if not openai_client:
        return "OpenAI API key is not configured. Please set OPENAI_API_KEY."

    # Route to a context based on registry docs using a small model
    selected_name = await asyncio.to_thread(_route_context_name, user_message)
    ctx = get_context_by_name(selected_name) if selected_name else get_default_context()
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
        model_to_use = getattr(ctx, "model", 'gpt-4.1')
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        kwargs = {
            "model": model_to_use,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 400,
        }
        if getattr(ctx, "tools", None):
            kwargs["tools"] = ctx.tools  # type: ignore[assignment]
            kwargs["tool_choice"] = "auto"

        # First call — model may request tool calls
        first = openai_client.chat.completions.create(**kwargs)
        if not first.choices:
            return ""
        msg = first.choices[0].message

        # If no tool calls, return content
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return (msg.content or "").strip()

        # Add assistant message that includes tool_calls
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        # Execute tools locally and append tool results
        for tc in tool_calls:
            tool_name = tc.function.name
            raw_args = tc.function.arguments or "{}"
            try:
                args = json.loads(raw_args)
            except Exception:
                args = {}

            result_text = f"Tool '{tool_name}' not available."
            spec = TOOL_REGISTRY.get(tool_name)
            if spec:
                try:
                    result_text = spec.execute(args)
                except Exception as e:
                    result_text = f"Error executing tool '{tool_name}': {e}"

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tool_name,
                    "content": result_text,
                }
            )

        # Second call including tool results to produce final answer
        second = openai_client.chat.completions.create(
            model=model_to_use,
            messages=messages,
            temperature=0.7,
            max_tokens=400,
        )
        return (second.choices[0].message.content or "").strip() if second.choices else ""

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

    # If message starts with the command prefix, handle as a command only
    content_text = message.content or ""
    if content_text.startswith(PREFIX):
        await bot.process_commands(message)
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
