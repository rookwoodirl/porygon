import os
import asyncio
import json
import logging
import inspect
import re
import discord
import random
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

# Running event loop reference for cross-thread scheduling
_RUNNING_LOOP: asyncio.AbstractEventLoop | None = None

def get_bot_loop() -> asyncio.AbstractEventLoop | None:
    return _RUNNING_LOOP

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


def _extract_message_text(message: discord.Message) -> str:
    """Return the human-readable text for a discord.Message.

    Prefer `message.content`. If empty, extract embed title/description/fields.
    """
    try:
        # Prefer plain content
        content = (getattr(message, 'content', '') or '').strip()
        if content:
            return content

        # Fallback to embed contents
        parts: list[str] = []
        embeds = getattr(message, 'embeds', []) or []
        for e in embeds:
            try:
                title = getattr(e, 'title', None)
                desc = getattr(e, 'description', None)
                if title:
                    parts.append(str(title))
                if desc:
                    parts.append(str(desc))
                for f in getattr(e, 'fields', []) or []:
                    try:
                        parts.append(f"{getattr(f, 'name', '')}: {getattr(f, 'value', '')}")
                    except Exception:
                        continue
            except Exception:
                continue
        return " ".join(p for p in parts if p).strip()
    except Exception:
        return ""

def _embed_for_text(text: str, title: str | None = None) -> discord.Embed:
    """Create a consistent embed for bot responses."""
    md = ['#', '*', '>']
    sounds = ['beep', 'boop', 'bzzt', 'beep boop boop beep', 'bzzt bzzt', 'brrrrrrr']
    

    while '\n\n' in text:
        beep_boop = '\n'.join([ md[random.randint(0, len(md)-1)] + ' ' + sounds[random.randint(0, len(sounds)-1)] ])
        text = text.replace('\n\n', '\n```md\n' + beep_boop + '\n```', 1)
    embed = discord.Embed(description=text, color=0x2F3136)
    if title:
        embed.title = title
    return embed


async def _edit_message_embed(channel_id: str | int, message_id: str | int, text: str, title: str | None = None) -> None:
    """Fetch a message and edit it to contain `text` in an embed. Safe to call from event loop."""
    try:
        cid = int(channel_id)
        mid = int(message_id)
    except Exception:
        return
    try:
        ch = bot.get_channel(cid) or await bot.fetch_channel(cid)
        msg = await ch.fetch_message(mid)
        await msg.edit(embed=_embed_for_text(text, title=title), content=None)
    except Exception:
        # Best-effort; don't raise
        return


def _schedule_edit_placeholder(channel_id: str | int, message_id: str | int, text: str, title: str | None = None) -> None:
    """Schedule an edit of the placeholder embed from non-async threads."""
    try:
        loop = get_bot_loop()
        if not loop or not getattr(loop, "is_running", lambda: False)():
            return
        coro = _edit_message_embed(channel_id, message_id, text, title=title)
        asyncio.run_coroutine_threadsafe(coro, loop)
    except Exception:
        return


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
                tools=[ t['function']['name'] for t in tools ],
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
    global _RUNNING_LOOP
    try:
        _RUNNING_LOOP = asyncio.get_running_loop()
    except Exception:
        _RUNNING_LOOP = None
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is in {len(bot.guilds)} guilds')

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(embed=_embed_for_text(f"Command not found. Use `{PREFIX}help` to see available commands."))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=_embed_for_text(f"Missing required argument. Use `{PREFIX}help {ctx.command}` for usage."))
    else:
        logger.error(f"An error occurred: {error}")
        await ctx.send(embed=_embed_for_text("An error occurred while processing the command."))

@bot.command(name='pokedle')
async def pokedle(ctx):
    """Start a Pokedle game in a thread. Uses `games.pokedle.PokedleSession` if available."""
    try:
        import importlib
        mod = importlib.import_module('games.pokedle')
    except Exception:
        await ctx.send(embed=_embed_for_text("Pokedle game is not available on this bot."))
        return

    PokedleSession = getattr(mod, 'PokedleSession', None)
    if PokedleSession is None:
        await ctx.send(embed=_embed_for_text("Pokedle module present but session class not found."))
        return

    try:
        starter = await ctx.send(f"{ctx.author.mention} is starting a Pokedle game... creating thread...")
        thread = await starter.create_thread(name=f"Pokedle — {ctx.author.display_name}", auto_archive_duration=60)
        bot_msg = await thread.send("Preparing game...")
        session = PokedleSession(bot, ctx.channel, ctx.author)
        # run session as background task
        asyncio.create_task(session.run(thread, bot_msg))
        await ctx.send(embed=_embed_for_text(f"Pokedle started in thread {thread.mention}"))
    except Exception as e:
        await ctx.send(embed=_embed_for_text(f"Failed to start Pokedle: {e}"))

@bot.command(name='ping')
async def ping(ctx):
    """Simple ping command to test bot responsiveness."""
    latency = round(bot.latency * 1000)
    await ctx.send(embed=_embed_for_text(f'Pong! Latency: {latency}ms'))

@bot.command(name='hello')
async def hello(ctx):
    """Say hello to the user."""
    await ctx.send(embed=_embed_for_text(f'Hello {ctx.author.mention}! I am Porygon, your Discord bot!'))


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


async def _get_openai_reply(
    chat_history: list,
    placeholder_channel_id: str | None = None,
    placeholder_message_id: str | None = None,
) -> str:
    """Call OpenAI to generate a reply using provided context."""
    if not openai_client:
        return "OpenAI API key is not configured. Please set OPENAI_API_KEY."

    # Extract the latest user message and metadata from chat_history (list of discord.Message)
    last_user_message: str = ""
    discord_user_id: str | None = None
    discord_username: str | None = None
    try:
        for m in reversed(chat_history):
            # Treat any message not authored by the bot as a user message
            author = getattr(m, 'author', None)
            is_bot = bool(author == bot.user or getattr(author, 'bot', False))
            if not is_bot:
                content_val = (getattr(m, 'content', '') or '').strip()
                last_user_message = content_val
                try:
                    discord_user_id = str(getattr(author, 'id', '')) or None
                    discord_username = getattr(author, 'display_name', None) or getattr(author, 'name', None)
                except Exception:
                    pass
                break
    except Exception:
        last_user_message = last_user_message or ""
    
    metadata = {
        'author_id' : discord_user_id,
        'message_id' : m.id,
        'channel_id' : m.channel.id,
        'attachments' : m.attachments
    }

    # Prepare a lightweight history for routing (exclude the latest turn to avoid duplication)
    router_history: list[dict] = []
    try:
        for m in list(chat_history)[:-1]:
            author = getattr(m, 'author', None)
            role = "assistant" if (author == bot.user or getattr(author, 'bot', False)) else "user"
            author_name = getattr(author, 'display_name', None) or getattr(author, 'name', None) or "user"
            content = _extract_message_text(m).replace("\n", " ")
            if content:
                router_history.append({"role": role, "content": f"{author_name}: {content}"})
    except Exception:
        router_history = []

    # Route to a context based on registry docs using a small model
    selected_name = await asyncio.to_thread(
        _route_context_name,
        router_history,
        last_user_message,
        discord_user_id,
        discord_username,
    )
    ctx = get_context_by_name(selected_name) if selected_name else get_default_context()
    system_prompt = ctx.prompt

    # Build chat messages: prior history as separate turns, then the current user message
    def build_messages():
        """Converts discord chat history to openai message history."""
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        # Append turns from chat_history (list of discord.Message)
        for m in chat_history:
            try:
                author = getattr(m, 'author', None)
                role = "assistant" if (author == bot.user or getattr(author, 'bot', False)) else "user"
                author_name = getattr(author, 'display_name', None) or getattr(author, 'name', None) or "user"
                content = _extract_message_text(m)
                if not content:
                    continue
                # Add name prefix to aid multi-user disambiguation in channels
                messages.append({"role": role, "content": f"{author_name}: {content}"})
            except Exception:
                continue
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

        # Iterative loop: model -> (optional) tool calls -> model, up to max iterations
        max_iterations = 3
        tool_funcs = get_tool_functions()
        for iteration in range(max_iterations):
            # Ensure kwargs messages reflect current messages list
            kwargs["messages"] = messages
            resp = openai_client.chat.completions.create(**kwargs)
            try:
                _record_billing(
                    context_name=selected_name or "default",
                    model=model_to_use,
                    messages=messages,
                    tools=ctx.tools if hasattr(ctx, 'tools') else None,
                    usage_obj=getattr(resp, 'usage', {}),
                    discord_user_id=discord_user_id,
                    discord_username=discord_username,
                )
            except Exception:
                pass

            if not resp.choices:
                return ""
            msg = resp.choices[0].message

            # If no tool calls, return content (and update placeholder if present)
            tool_calls = getattr(msg, "tool_calls", None)
            content_only = _strip_name_prefixes((msg.content or "").strip())
            if not tool_calls:
                try:
                    if placeholder_channel_id and placeholder_message_id:
                        _schedule_edit_placeholder(placeholder_channel_id, placeholder_message_id, content_only)
                except Exception:
                    pass
                return content_only

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

                # Update placeholder to indicate which tool is being called
                try:
                    if placeholder_channel_id and placeholder_message_id:
                        _schedule_edit_placeholder(placeholder_channel_id, placeholder_message_id, f"\n```md\n<calling {tool_name}...>\n```\n")
                except Exception:
                    pass

                result_text = f"Tool '{tool_name}' not available."
                fn = tool_funcs.get(tool_name)
                if fn:
                    try:
                        # Inject requesting_discord_id only if the function accepts that parameter
                        try:
                            sig = inspect.signature(fn)

                            # update toolcall with metadata the bot might not have access to
                            if isinstance(args, dict):
                                args.update({ k : v for k, v in metadata.items() if k in sig.parameters })
                            
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

            # Continue loop for next model call which will include the appended tool results

        # If we exit the loop without a model response without tool_calls, make one final call
        try:
            kwargs["messages"] = messages
            final_resp = openai_client.chat.completions.create(
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
                    usage_obj=getattr(final_resp, 'usage', {}),
                    discord_user_id=discord_user_id,
                    discord_username=discord_username,
                )
            except Exception:
                pass
            final = _strip_name_prefixes((final_resp.choices[0].message.content or "").strip()) if getattr(final_resp, 'choices', None) else ""
            try:
                if placeholder_channel_id and placeholder_message_id:
                    _schedule_edit_placeholder(placeholder_channel_id, placeholder_message_id, final)
            except Exception:
                pass
            logger.info("response: %s", final_resp.choices[0].message.content if getattr(final_resp, 'choices', None) else None)
            return final
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return ""

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

    # Collect previous 9 messages to pair with current = total 10 (list of discord.Message)
    chat_history: list[discord.Message] = []
    try:
        async for msg in message.channel.history(limit=9, oldest_first=False):
            if msg.id == message.id:
                continue
            chat_history.insert(0, msg)
    except Exception as e:  # pragma: no cover
        logger.debug(f"Could not fetch history for context: {e}")

    # Trim to last 9 prior messages
    chat_history = chat_history[-9:]

    # Include the current message as the latest user turn
    chat_history.append(message)

    # Send an initial hourglass embed so users see we are working
    placeholder_msg = None
    try:
        placeholder_msg = await message.reply(embed=_embed_for_text("⌛ working..."))
    except Exception:
        placeholder_msg = None

    # Prepare placeholder ids to let the background worker update the embed
    placeholder_channel_id = None
    placeholder_message_id = None
    try:
        if placeholder_msg:
            placeholder_channel_id = str(getattr(placeholder_msg.channel, 'id', getattr(message.channel, 'id', None)))
            placeholder_message_id = str(getattr(placeholder_msg, 'id', None))
    except Exception:
        placeholder_channel_id = None
        placeholder_message_id = None

    reply_text = await _get_openai_reply(
        chat_history,
        placeholder_channel_id,
        placeholder_message_id,
    )
    if reply_text:
        try:
            # If we have a placeholder, update it with the final response
            if placeholder_msg:
                try:
                    await placeholder_msg.edit(embed=_embed_for_text(reply_text), content=None)
                except Exception:
                    # Fallback to sending a new reply
                    if isinstance(reply_text, str) and len(reply_text) <= 4096:
                        await message.reply(embed=_embed_for_text(reply_text))
                    else:
                        max_chunk = 4000
                        parts = [reply_text[i:i+max_chunk] for i in range(0, len(reply_text), max_chunk)]
                        for p in parts:
                            await message.reply(p)
            else:
                if isinstance(reply_text, str) and len(reply_text) <= 4096:
                    await message.reply(embed=_embed_for_text(reply_text))
                else:
                    max_chunk = 4000
                    parts = [reply_text[i:i+max_chunk] for i in range(0, len(reply_text), max_chunk)]
                    for p in parts:
                        await message.reply(p)
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
