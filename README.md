# Porygon Discord Bot

A Discord bot built with Python using discord.py.

## Setup

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Create a `.env` file in the project root with your Discord bot token:
   ```bash
   cp .env.example .env
   ```
   
3. Edit the `.env` file and add your Discord bot token:
   ```
   DISCORD_TOKEN=your_actual_discord_bot_token_here
   # Optional: if you use a separate dev bot/token
   DISCORD_TOKEN_DEV=your_dev_discord_bot_token_here
   # Optional: set to "development" to use DISCORD_TOKEN_DEV
   ENVIRONMENT=production
   ```

4. Provide OpenAI credentials in `.env`:
   ```
   OPENAI_API_KEY=sk-...
   # Optional: override model (defaults to gpt-4.5)
   OPENAI_MODEL=gpt-4.5
   ```

5. Run the bot:
   ```bash
   python main.py
   ```

## Environment Variables

- `DISCORD_TOKEN` (required): Your Discord bot token
- `DISCORD_TOKEN_DEV` (optional): Used only when `ENVIRONMENT=development`
- `COMMAND_PREFIX` (optional): Command prefix for the bot (default: `!`)
- `DEBUG` (optional): Enable debug logging (default: `false`)
- `DATABASE_URL` (optional): PostgreSQL connection string for Railway (e.g., `postgresql://user:pass@host:port/db`)
 - `OPENAI_API_KEY` (optional): Required to enable OpenAI responses to messages
 - `OPENAI_MODEL` (optional): Defaults to `gpt-4.5`
- `ENVIRONMENT` (optional): Set to `development` to use `DISCORD_TOKEN_DEV`; any other value (or unset) uses `DISCORD_TOKEN`

## Commands
## AI Autoreply Behavior

The bot replies to each user message using OpenAI. It sends the model a compact context of the first 200 characters of the last 10 messages with usernames to keep continuity. Disable or adjust in `on_message` if needed.
## Using Postgres

Create the client:

```python
from postgres import PorygonPostgres
import os

db = PorygonPostgres(os.environ["DATABASE_URL"])  # requires DATABASE_URL in .env

# SELECT example
result = db.run_query("SELECT 1 AS one")
print(result.rows)       # [{"one": 1}]
print(result.rowcount)   # 1

# INSERT/UPDATE/DELETE example
affected = db.run_query("UPDATE table SET col = %s WHERE id = %s", ["value", 123])
print(affected)
```

For bulk operations, pass `many=True` with an iterable of param sequences.

- `!ping` - Check bot latency
- `!hello` - Get a greeting from the bot
- `!help` - Show available commands

## Getting a Discord Bot Token

1. Go to https://discord.com/developers/applications
2. Create a new application
3. Go to the "Bot" section
4. Create a bot and copy the token
5. Invite the bot to your server with appropriate permissions
