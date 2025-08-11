import os
import asyncio
import json
import logging
import inspect
import re
import discord
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI
from context import (
    get_context_by_name,
    get_context_options,
    get_default_context,
)
from tools import get_tool_functions
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from db.models import Billing

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
ROUTER_MODEL = os.getenv('ROUTER_MODEL', 'gpt-5-mini')

if DEBUG:
    logging.getLogger().setLevel(logging.DEBUG)

# Define intents (admin-level: enable all, including privileged)
intents = discord.Intents.all()
intents.message_content = True  # Ensure message content is enabled for prefix commands

# Create bot instance
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ---------- billing helpers ----------
_BillingSessionFactory: sessionmaker | None = None


def _get_billing_session_factory() -> sessionmaker | None:
    global _BillingSessionFactory
    if _BillingSessionFactory is not None:
        return _BillingSessionFactory
    dsn = os.getenv('DATABASE_URL')
    if not dsn:
        return None
    try:
        engine = create_engine(dsn, future=True)
        _BillingSessionFactory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    except Exception:
        _BillingSessionFactory = None
    return _BillingSessionFactory
def _strip_name_prefixes(text: str) -> str:
    if not isinstance(text, str):
        return text
    lowered = text.lstrip()
    for prefix in ("Porygon:", "Porygon2:", "Porygon :", "Porygon2 :"):
        if lowered.startswith(prefix):
            return lowered[len(prefix):].lstrip()
    return text


def _is_directed_to_bot(message: discord.Message) -> bool:
    """Heuristic gate to decide if we should respond.
    - True for DMs
    - True if the bot is mentioned
    - True if content references 'pory' or 'porygon' as a word/prefix
    """
    try:
        # Direct messages
        if isinstance(message.channel, discord.DMChannel):
            return True
    except Exception:
        pass

    try:
        # Mentions
        if bot.user and any(getattr(u, 'id', None) == bot.user.id for u in getattr(message, 'mentions', []) or []):
            return True
    except Exception:
        pass

    text = (message.content or "").strip()
    if not text:
        return False
    lower = text.lower()

    # Name cues (word boundary or common punctuation right after name)
    if re.search(r"\b(pory|porygon)\b", lower):
        return True
    if lower.startswith("pory ") or lower.startswith("pory:") or lower.startswith("pory,"):
        return True
    if lower.startswith("porygon ") or lower.startswith("porygon:") or lower.startswith("porygon,"):
        return True

    return False


def _extract_tool_names(tool_schemas: list[dict] | None) -> list[str]:
    names: list[str] = []
    if not tool_schemas:
        return names
    for t in tool_schemas:
        try:
            fn = t.get('function', {})
            if isinstance(fn, dict) and isinstance(fn.get('name'), str):
                names.append(fn['name'])
        except Exception:
            continue
    return names


def _record_billing(
    context_name: str,
    model: str,
    messages: list[dict],
    tools: list[dict] | None,
    usage_obj: object,
    discord_user_id: str | None = None,
    discord_username: str | None = None,
) -> None:
    sf = _get_billing_session_factory()
    if not sf:
        return
    tokens_in = 0
    tokens_out = 0
    try:
        usage = getattr(usage_obj, 'usage', usage_obj)
        tokens_in = int(getattr(usage, 'prompt_tokens', 0) or 0)
        tokens_out = int(getattr(usage, 'completion_tokens', 0) or 0)
    except Exception:
        try:
            tokens_in = int(usage_obj.get('prompt_tokens', 0))  # type: ignore[attr-defined]
            tokens_out = int(usage_obj.get('completion_tokens', 0))  # type: ignore[attr-defined]
        except Exception:
            tokens_in = tokens_in or 0
            tokens_out = tokens_out or 0
    try:
        with sf() as s:
            s.add(Billing(
                context_name=context_name,
                model=model,
                prompt=json.dumps(messages, ensure_ascii=False),
                tools=_extract_tool_names(tools),
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                discord_user_id=discord_user_id,
                discord_username=discord_username,
            ))
            s.commit()
    except Exception:
        # never break user flow on billing failures
        pass

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


def _route_context_name(
    chat_history: list[dict] | None,
    user_message: str,
    discord_user_id: str | None = None,
    discord_username: str | None = None,
) -> str | None:
    """Use a small model to pick a context name from the registry. Uses recent chat history plus the latest user message. Returns None for default."""
    options = get_context_options()
    if not options or not openai_client:
        return None

    option_block = "\n".join(f"- {opt['name']}: {opt['doc']}" for opt in options)
    sys_msg = (
        "You are a context router. Choose the single best context name from the list based on the user's message and recent conversation history.\n"
        "If none clearly apply, output 'default'.\n"
        "Output ONLY the name with no extra words."
    )

    # Build a concise conversation history string if provided
    history_block = ""
    try:
        if chat_history:
            parts: list[str] = []
            for m in chat_history:
                role = m.get("role", "user")
                content = (m.get("content") or "").replace("\n", " ")
                parts.append(f"{role}: {content}")
            history_block = "\n".join(parts)
    except Exception:
        history_block = ""

    user_msg = (
        f"Contexts:\n{option_block}\n\n"
        f"Conversation history:\n{history_block}\n\n"
        f"Latest user message:\n{user_message}\n\n"
        "Answer with just the context name."
    )

    try:
        router_messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ]
        resp = openai_client.chat.completions.create(
            model=ROUTER_MODEL,
            messages=router_messages,
            max_completion_tokens=400,
        )
        # Record router billing as its own entry (orchestrator)
        try:
            _record_billing(
                context_name="orchestrator",
                model=ROUTER_MODEL,
                messages=router_messages,
                tools=None,
                usage_obj=getattr(resp, 'usage', {}),
                discord_user_id=discord_user_id,
                discord_username=discord_username,
            )
        except Exception:
            pass
        name = (resp.choices[0].message.content or "").strip()
        print('Chosen context: ', name)
        if name.lower() == 'default' or not name:
            return None
        # ensure it exists
        existing = {opt['name'] for opt in options}
        return name if name in existing else None
    except Exception:
        return None


async def _generate_openai_reply(
    chat_history: list[dict],
    user_message: str,
    channel_name: str | None,
    discord_user_id: str | None,
    discord_username: str | None,
) -> str:
    """Call OpenAI to generate a reply using provided context."""
    if not openai_client:
        return "OpenAI API key is not configured. Please set OPENAI_API_KEY."

    # Route to a context based on registry docs using a small model
    selected_name = await asyncio.to_thread(
        _route_context_name,
        chat_history,
        user_message,
        discord_user_id,
        discord_username,
    )
    ctx = get_context_by_name(selected_name) if selected_name else get_default_context()
    system_prompt = ctx.prompt

    # Build chat messages: prior history as separate turns, then the current user message
    def build_messages():
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        # Append prior turns (already trimmed)
        for m in chat_history:
            if m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str):
                messages.append({"role": m["role"], "content": m["content"]})
        # Current user turn
        messages.append({"role": "user", "content": user_message})
        return messages

    def _call_openai():
        model_to_use = ctx.model
        messages = build_messages()

        kwargs = {
            "model": model_to_use,
            "messages": messages,
            "max_completion_tokens": ctx.max_completion_tokens,
        }

        if getattr(ctx, "tools", None):
            kwargs["tools"] = ctx.tools  # type: ignore[assignment]
            kwargs["tool_choice"] = "auto"

        # First call — model may request tool calls
        first = openai_client.chat.completions.create(**kwargs)
        try:
            _record_billing(
                context_name=selected_name or "default",
                model=model_to_use,
                messages=messages,
                tools=ctx.tools if hasattr(ctx, 'tools') else None,
                usage_obj=getattr(first, 'usage', {}),
                discord_user_id=discord_user_id,
                discord_username=discord_username,
            )
        except Exception:
            pass
        if not first.choices:
            return ""
        msg = first.choices[0].message

        # If no tool calls, return content
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return _strip_name_prefixes((msg.content or "").strip())

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
        tool_funcs = get_tool_functions()
        for tc in tool_calls:
            tool_name = tc.function.name
            raw_args = tc.function.arguments or "{}"
            try:
                args = json.loads(raw_args)
            except Exception:
                args = {}
            # Inject requesting discord id into tool args so tool-level caching can record it
            # Defer injection of requesting_discord_id until we know the target fn accepts it

            result_text = f"Tool '{tool_name}' not available."
            fn = tool_funcs.get(tool_name)
            if fn:
                try:
                    # Inject requesting_discord_id only if the function accepts that parameter
                    try:
                        sig = inspect.signature(fn)
                        if discord_user_id is not None and "requesting_discord_id" in sig.parameters and isinstance(args, dict) and "requesting_discord_id" not in args:
                            args["requesting_discord_id"] = discord_user_id
                    except Exception:
                        # If signature inspection fails, skip injection
                        pass

                    result_text = fn(**args)
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
            max_completion_tokens=ctx.max_completion_tokens,
        )
        try:
            _record_billing(
                context_name=selected_name or "default",
                model=model_to_use,
                messages=messages,
                tools=ctx.tools if hasattr(ctx, 'tools') else None,
                usage_obj=getattr(second, 'usage', {}),
                discord_user_id=discord_user_id,
                discord_username=discord_username,
            )
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            pass
        # Log the final response (use proper logging level API)
        logger.info("response: %s", second.choices[0].message.content)
        return _strip_name_prefixes((second.choices[0].message.content or "").strip()) if second.choices else ""

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

    # If it does not look directed at the bot, skip responding
    if not _is_directed_to_bot(message):
        await bot.process_commands(message)
        return

    # Collect previous 9 messages (first 200 chars) to pair with current = total 10
    # Build structured chat history with roles
    chat_history: list[dict] = []
    try:
        async for msg in message.channel.history(limit=9, oldest_first=False):
            if msg.id == message.id:
                continue
            author_name = getattr(msg.author, 'display_name', None) or msg.author.name
            content = (msg.content or "").replace("\n", " ")[:200]
            if not content:
                continue
            role = "assistant" if msg.author == bot.user else "user"
            # Include author tag for disambiguation
            chat_history.insert(0, {"role": role, "content": f"{author_name}: {content}"})
    except Exception as e:  # pragma: no cover
        logger.debug(f"Could not fetch history for context: {e}")

    # Trim to last 9 prior messages
    chat_history = chat_history[-9:]

    # Channel name best-effort (DMs may not have a name)
    try:
        channel_name = getattr(message.channel, "name", None)
    except Exception:
        channel_name = None

    # Generate and send reply
    # Prepare user identifiers for billing
    try:
        _discord_user_id = str(message.author.id)
    except Exception:
        _discord_user_id = None
    try:
        _discord_username = getattr(message.author, 'display_name', None) or message.author.name
    except Exception:
        _discord_username = None

    reply_text = await _generate_openai_reply(
        chat_history,
        message.content or "",
        channel_name,
        _discord_user_id,
        _discord_username,
    )
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
