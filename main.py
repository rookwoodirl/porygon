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

from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from db.models import Billing
from util.embeds import embed_for_text
from commands.basic import setup_basic_commands
from commands.pokedle import setup_pokedle_commands
from commands.lolcustom import setup_lolcustom

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

_embed_for_text = embed_for_text


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

# Register commands from command modules
setup_basic_commands(bot)
setup_pokedle_commands(bot)
setup_lolcustom(bot)


def get_context_options() -> list[dict]:
    """Temporary stub for context routing; returns empty list to use default behavior."""
    return []



async def _get_openai_reply(
    chat_history: list,
    placeholder_channel_id: str | None = None,
    placeholder_message_id: str | None = None,
) -> str:
    """Call OpenAI to generate a reply using provided tools (no Context)."""
    if not openai_client:
        return "OpenAI API key is not configured. Please set OPENAI_API_KEY."

    # Last human message and metadata
    try:
        last_human = next(m for m in reversed(chat_history) if not getattr(getattr(m, 'author', None), 'bot', False))
    except StopIteration:
        last_human = chat_history[-1] if chat_history else None

    author_name = getattr(getattr(last_human, 'author', None), 'name', None)
    author_id = getattr(getattr(last_human, 'author', None), 'id', None)
    channel_id = getattr(getattr(last_human, 'channel', None), 'id', None)
    message_id = getattr(last_human, 'id', None)
    try:
        attachments = list(getattr(last_human, 'attachments', []) or [])
    except Exception:
        attachments = []

    metadata = {
        "author_id": str(author_id) if author_id is not None else None,
        "channel_id": str(channel_id) if channel_id is not None else None,
        "message_id": str(message_id) if message_id is not None else None,
        "attachments": attachments,
    }

    def _discord_to_openai_messages(discord_messages: list) -> list[dict]:
        messages: list[dict] = []
        for m in discord_messages:
            try:
                role = 'assistant' if getattr(getattr(m, 'author', None), 'bot', False) else 'user'
                text = _extract_message_text(m) or ""
                if not text:
                    continue
                messages.append({"role": role, "content": text})
            except Exception:
                continue
        return messages

    async def _openai_call(messages: list[dict], model: str = 'gpt-5-mini', max_tokens: int = 2000, tools: list[dict] | None = None):
        kwargs = {
            "model": model,
            "messages": messages,
            "tools": tools or None,
            "max_completion_tokens": max_tokens,
        }
        return await asyncio.to_thread(openai_client.chat.completions.create, **kwargs)

    def _call_tool(tool_name: str, kwargs: dict) -> str:
        fn = TOOL_FUNCTIONS.get(tool_name)
        if not fn:
            return f"Tool '{tool_name}' is not available."
        try:
            sig = inspect.signature(fn)
            safe_kwargs: dict = {}
            for key, value in (kwargs or {}).items():
                if key in sig.parameters:
                    safe_kwargs[key] = value
            for key, value in metadata.items():
                if key in sig.parameters and value is not None:
                    safe_kwargs[key] = value
            result = fn(**safe_kwargs)
            return str(result) if result is not None else ""
        except Exception as e:
            return f"Error running tool '{tool_name}': {e}"

    # Orchestrator selects tools and an execution prompt
    async def _orchestrator(discord_messages: list) -> tuple[str, list[str]]:
        tool_lines = []
        for schema in TOOL_SCHEMAS:
            try:
                fn_name = schema.get('function', {}).get('name', '')
                fn_desc = schema.get('function', {}).get('description', '')
                if fn_name:
                    tool_lines.append(f"- {fn_name}: {fn_desc}")
            except Exception:
                continue
        convo = []
        for m in discord_messages[-10:]:
            try:
                who = m.author.id
                txt = (_extract_message_text(m) or '').replace('\n', ' ')
                if txt:
                    convo.append(f"{who}: {txt}")
            except Exception:
                continue
        system_prompt = (
            "Your goal is to summarize the context of this conversation into a prompt a subsequent model can complete."
            "Response exclusively in valid JSON format:"
            """
            { "prompt" : "Complete this task...", "tools" : ["a", "b", "c", ...] }
            """
        )
        user_prompt = (
            "Available tools:\n" + "\n".join(tool_lines) + "\n\n" +
            "Conversation (most recent last):\n" + "\n".join([c[:200] for c in convo]) + "\n\n" +
            "Output JSON with keys 'prompt' (string) and 'tools' (array of tool names)."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        all_tool_names = [
            (s.get('function', {}) or {}).get('name')
            for s in TOOL_SCHEMAS
            if (s.get('function', {}) or {}).get('name')
        ]
        try:
            resp = await _openai_call(messages, model=ROUTER_MODEL, max_tokens=400, tools=None)
            try:
                asyncio.create_task(asyncio.to_thread(
                    _record_billing,
                    context_name="orchestrator",
                    model=ROUTER_MODEL,
                    messages=messages,
                    tools=None,
                    usage_obj=getattr(resp, 'usage', {}),
                    discord_user_id=str(author_id) if author_id is not None else None,
                    discord_username=str(author_name) if author_name else None,
                ))
            except Exception:
                pass
            content = (resp.choices[0].message.content or "").strip()
            json_text = content
            print('json_text:', json_text)
            try:
                import re as _re
                m = _re.search(r"\{[\s\S]*\}", content)
                if m:
                    json_text = m.group(0)
            except Exception:
                pass
            if not json_text:
                last_user_text = (_extract_message_text(last_human) or "").strip() if last_human else ""
                default_prompt = (
                    "You are a helpful Discord assistant. Be concise and helpful. "
                    f"Respond to the user's latest message: {last_user_text}"
                )
                return default_prompt, all_tool_names
            data = json.loads(json_text)
            prompt_text = str(data.get('prompt', '')).strip()
            tool_names = [t for t in (data.get('tools') or []) if isinstance(t, str)]
            print('Prompt:', prompt_text)
            print('Tools:', ', '.join(tool_names))
            if not prompt_text:
                last_user_text = (_extract_message_text(last_human) or "").strip() if last_human else ""
                prompt_text = (
                    "You are a helpful Discord assistant. Be concise and helpful. "
                    f"Respond to the user's latest message: {last_user_text}"
                )
            if not tool_names:
                tool_names = []
            return prompt_text, tool_names
        except Exception as e:
            print(e)
            return (
                "You are a helpful assistant for Discord. Answer succinctly and safely.",
                []
            )

    prompt_text, selected_tool_names = await _orchestrator(chat_history)
    name_to_schema = {s.get('function', {}).get('name'): s for s in TOOL_SCHEMAS}
    selected_tool_schemas = [name_to_schema[n] for n in selected_tool_names if n in name_to_schema]

    executor_messages: list[dict] = []
    if prompt_text:
        executor_messages.append({"role": "system", "content": prompt_text})
    executor_messages.extend(_discord_to_openai_messages(chat_history))

    def _serialize_tool_call(tc) -> dict:
        try:
            tc_id = getattr(tc, 'id', None) or tc.get('id')
        except Exception:
            tc_id = None
        try:
            fn_obj = getattr(tc, 'function', None) or tc.get('function', {})
            fn_name = getattr(fn_obj, 'name', None) or fn_obj.get('name')
            fn_args = getattr(fn_obj, 'arguments', None) or fn_obj.get('arguments')
        except Exception:
            fn_name, fn_args = None, None
        return {
            "id": tc_id,
            "type": "function",
            "function": {
                "name": fn_name,
                "arguments": fn_args if isinstance(fn_args, str) else json.dumps(fn_args or {}),
            },
        }

    response = None
    for iteration in range(5):
        response = await _openai_call(
            executor_messages,
            model=os.getenv('CHAT_MODEL', 'gpt-5-mini'),
            max_tokens=2000,
            tools=selected_tool_schemas or None,
        )
        try:
            asyncio.create_task(asyncio.to_thread(
                _record_billing,
                context_name="execution",
                model=os.getenv('CHAT_MODEL', 'gpt-5-mini'),
                messages=executor_messages,
                tools=selected_tool_schemas or None,
                usage_obj=getattr(response, 'usage', {}),
                discord_user_id=str(author_id) if author_id is not None else None,
                discord_username=str(author_name) if author_name else None,
            ))
        except Exception:
            pass

        choice_msg = response.choices[0].message
        tool_calls = getattr(choice_msg, 'tool_calls', None) or []
        content_text = (getattr(choice_msg, 'content', None) or "").strip()


        if not tool_calls:
            return content_text or ""

        # Append the assistant tool call message
        assistant_msg = {
            "role": "assistant",
            "content": content_text,
            "tool_calls": [_serialize_tool_call(tc) for tc in tool_calls],
        }
        executor_messages.append(assistant_msg)

        # Execute each tool and append tool results
        tc_iterations = 0
        for tc in tool_calls:
            tc_iterations += 1
            try:
                fn_obj = getattr(tc, 'function', None) or tc.get('function', {})
                tool_name = getattr(fn_obj, 'name', None) or fn_obj.get('name')
                raw_args = getattr(fn_obj, 'arguments', None) or fn_obj.get('arguments')
            except Exception:
                tool_name, raw_args = None, None
            try:
                args_obj = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except Exception:
                args_obj = {}
            # Update placeholder with tool call details
            if placeholder_channel_id and placeholder_message_id:
                try:
                    headline = f'!iteration {iteration} / 5, tool_call {tc_iterations} / {len(tool_calls)}'
                    pretty_args = '\n\t'.join([f'{k} : {str(v)[:20]}' for k, v in (args_obj or {}).items()])
                    
                    _schedule_edit_placeholder(
                        placeholder_channel_id,
                        placeholder_message_id,
                        f"Running tools...\n```yaml\n{headline}\n{tool_name or 'unknown_tool'}\n\t{pretty_args}```"
                    )
                except Exception:
                    pass
            # Build safe kwargs and inject metadata when accepted
            fn = TOOL_FUNCTIONS.get(tool_name or "")
            if fn is None:
                result_text = "Tool not available"
            else:
                try:
                    sig = inspect.signature(fn)
                    safe_kwargs: dict = {}
                    for key, value in (args_obj or {}).items():
                        if key in sig.parameters:
                            safe_kwargs[key] = value
                    for key, value in metadata.items():
                        if key in sig.parameters and value is not None:
                            safe_kwargs[key] = value
                    result_text = await asyncio.to_thread(fn, **safe_kwargs)
                except Exception as e:
                    result_text = f"Error running tool '{tool_name}': {e}"
            tool_msg = {"role": "tool", "content": str(result_text)}
            try:
                tool_msg["tool_call_id"] = getattr(tc, 'id', None) or tc.get('id')
            except Exception:
                pass
            executor_messages.append(tool_msg)

    try:
        names = []
        for tc in (getattr(response.choices[0].message, 'tool_calls', None) or []):
            try:
                fn_obj = getattr(tc, 'function', None) or tc.get('function', {})
                nm = getattr(fn_obj, 'name', None) or fn_obj.get('name')
                if nm:
                    names.append(nm)
            except Exception:
                continue
        names_str = ", ".join(names)
    except Exception:
        names_str = ""
    return f"I tried to resolve your request but couldn't complete it via tools ({names_str}). Please try again."

        


    





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
        placeholder_msg = await message.reply(embed=_embed_for_text("```md\n<thinking ...>```"))
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
