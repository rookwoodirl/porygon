# Porygon — Discord bot

Small Discord bot that integrates with OpenAI and the Riot Games API and exposes a few utilities and games. Designed to run with a PostgreSQL backend for persistent data (accounts, logs, matches, billing).

## Highlights
- Commands are implemented under `commands/` and registered from `main.py`.
- Utilities live in `util/` (Riot API client, account linking, team balancing helpers, embed helpers).
- Database models and migrations are in `db/` and use SQLAlchemy with a `porygon` schema.
- Optional games live under `games/` (e.g. Pokedle).

## Architecture

- `main.py` — bot bootstrap, event loop wiring, command registration, OpenAI orchestration.
- `commands/` — command modules. Each file exposes a setup function which registers commands and event listeners on the bot instance:
  - `commands/basic.py` — `!ping`, `!hello`, `!lollink` (link Riot account)
  - `commands/pokedle.py` — `!pokedle` (game starter using `games/pokedle` if present)
  - `commands/lolcustom.py` — `!lolcustom`, `!lolcustom_test`, reaction handlers and embeds for the LoL custom queue
- `util/` — small helpers and API clients:
  - `util/riot.py` — thin Riot API client (`RiotApiClient`) with helpers for LoL/TFT and accounts endpoints.
  - `util/accounts.py` — convenience helpers to link PUUIDs to Discord IDs (uses SQLAlchemy session factory).
  - `util/lolcustom.py` — queueing, player voting, team planning and balancing algorithm (role constraints + LP balancing).
  - `util/embeds.py` — consistent embed creation helper used across commands.

## Database (Postgres)

This project expects a PostgreSQL database reachable via the `DATABASE_URL` environment variable. SQLAlchemy models are defined in `db/models.py` and include tables for:

- `users`, `messages` — basic bot records
- `summoners`, `accounts` — Riot summoner data and links between Discord IDs and Riot PUUIDs
- `log_api` — API call logs (provider, endpoint, args, full_call)
- `matches_lol`, `matches_tft` — stored match payloads (JSONB)
- `billing`, `model_pricing` — usage and pricing records for OpenAI billing

Migrations are managed under `db/migrations` (Alembic). The models use the `porygon` schema by default.

## Commands (user-facing)

- `!ping` — returns bot latency.
- `!hello` — friendly greeting.
- `!lollink RiotName#TAG` — links the calling Discord account to a Riot account (stores PUUID).
- `!lolcustom` — creates a LoL custom queue message. Users react with role emojis (TOP/JGL/MID/BOT/SUP). When 10 players have reacted, the bot balances two teams respecting chosen roles and minimizing LP difference.
  - The bot auto-adds role emojis to the queue message. Custom emoji overrides are supported via env vars `LOL_EMOJI_TOP`, `LOL_EMOJI_JGL`, etc.
- `!lolcustom_test` — generates a spoof 10-player set and prints the team plan (useful for local testing).
- `!pokedle` — starts the Pokedle game if `games/pokedle` is present.

## Utilities / Tools

- `util/riot.RiotApiClient` — wraps Riot endpoints with automatic retry handling and optional SQL logging of API calls.
- `util/lolcustom` — core logic for role collection, LP lookup (via linked PUUID), and team balancing. If no PUUID is linked, players default to 1400 LP.
- `util/accounts.link_puuid_to_discord` — helper used by `!lollink` to persist mapping.

## Configuration (env variables)

Create a `.env` with the following (examples):

```
DISCORD_TOKEN=your_production_bot_token
DISCORD_TOKEN_DEV=your_dev_token
ENVIRONMENT=development
OPENAI_API_KEY=sk-...
ROUTER_MODEL=gpt-5-mini
RIOT_API_KEY=RGAPI-...
RIOT_PLATFORM=na1
RIOT_REGION=americas
DATABASE_URL=postgresql://user:pass@localhost:5432/porygon
COMMAND_PREFIX=!
DEBUG=true
# Optional per-role emoji overrides (format: <:_name_:id>)
LOL_EMOJI_TOP=<:TOP:123456789012345678>
LOL_EMOJI_JGL=<:JGL:...>
```

## Development

1. Install dependencies (project uses `pyproject.toml`).
2. Create and configure a Postgres instance and set `DATABASE_URL`.
3. Run Alembic migrations in `db/` to create the schema.
4. Start the bot: `python main.py`

## Notes and extensions

- The LoL team balancing is intentionally conservative: it first attempts strict role assignments, then relaxes constraints minimizing role-violation penalties while minimizing LP difference.
- Riot API keys should be kept secret; the code falls back gracefully if the DB or Riot lookups fail (defaults to 1400 LP).
- Commands are modular under `commands/` — add new commands by creating a module with a setup function that accepts the bot instance and registers commands/listeners.

If you want, I can also add a usage example, contributing guide, or an `.env.example` file.

# alembic migration
uv run python -m db.migrate up
uv run python -m db.migrate status
uv run alembic revision --autogenerate -m "init"
uv run alembic upgrade head