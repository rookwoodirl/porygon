import json
import random
import sys
from ast import literal_eval
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


# Configuration of which attributes can be chosen and how to treat them
NUMERIC_ATTRS: List[str] = [
    "national_dex_number",
    "base_hp",
    "base_attack",
    "base_defense",
    "base_sp_attack",
    "base_sp_defense",
    "base_speed",
    "height_m",
    "weight_kg",
]

CATEGORY_ATTRS: List[str] = [
    "evolution_stage",
    "primary_type",
    "secondary_type",
    "egg_groups",
    "ev_yield_stat",
    "generation_first_introduced",
    "generations_present",
]

FRIENDLY_NAMES: Dict[str, str] = {
    "national_dex_number": "Nat. Dex #",
    "base_hp": "HP",
    "base_attack": "Atk",
    "base_defense": "Def",
    "base_sp_attack": "Sp.Atk",
    "base_sp_defense": "Sp.Def",
    "base_speed": "Spd",
    "height_m": "Height (m)",
    "weight_kg": "Weight (kg)",
    "evolution_stage": "Evo. Stage",
    "primary_type": "1st Type",
    "secondary_type": "2nd Type",
    "egg_groups": "Egg Groups",
    "ev_yield_stat": "EV Yield Stat",
    "generation_first_introduced": "First Gen",
    "generations_present": "All Gens",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def pokemon_csv_path() -> Path:
    return project_root() / "games" / "pokedex.json"


def _to_number(value: str) -> Optional[float]:
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        # Int-like numbers remain comparable as floats
        return float(value)
    except ValueError:
        return None


def _to_set_from_jsonish(value) -> Optional[Set[str]]:
    if value is None:
        return None
    # value may already be a list from JSON
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip() != ""}
    text = str(value).strip()
    if text == "":
        return set()
    # try to parse as JSON list
    try:
        parsed = literal_eval(text)
        if isinstance(parsed, (list, tuple, set)):
            return {str(item).strip() for item in parsed if str(item).strip() != ""}
    except Exception:
        pass
    return {text}


def _to_set_from_single(value: str) -> Optional[Set[str]]:
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return set()
    return {text}


def parse_row(entry: Dict[str, Any]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    # basic
    parsed["name"] = entry.get("name")
    parsed["name_normalized"] = (entry.get("name") or "").strip().lower()

    # numeric attrs
    parsed["national_dex_number"] = float(entry.get("national_dex")) if entry.get("national_dex") is not None else None
    bs = entry.get("base_stats") or {}
    parsed["base_hp"] = float(bs.get("hp")) if bs.get("hp") is not None else None
    parsed["base_attack"] = float(bs.get("attack")) if bs.get("attack") is not None else None
    parsed["base_defense"] = float(bs.get("defense")) if bs.get("defense") is not None else None
    parsed["base_sp_attack"] = float(bs.get("sp_attack")) if bs.get("sp_attack") is not None else None
    parsed["base_sp_defense"] = float(bs.get("sp_defense")) if bs.get("sp_defense") is not None else None
    parsed["base_speed"] = float(bs.get("speed")) if bs.get("speed") is not None else None
    parsed["height_m"] = float(entry.get("height_m")) if entry.get("height_m") is not None else None
    parsed["weight_kg"] = float(entry.get("weight_kg")) if entry.get("weight_kg") is not None else None

    # categories
    types = entry.get("types") or []
    types = [t for t in types if t and str(t).strip().lower() != "unknown"]
    parsed["primary_type"] = {types[0]} if len(types) >= 1 else set()
    parsed["secondary_type"] = {types[1]} if len(types) >= 2 else set()

    parsed["egg_groups"] = _to_set_from_jsonish(entry.get("egg_groups")) or set()

    # ev_yield_stat isn't available reliably; derive from ev_yield_total or meta if possible
    parsed["ev_yield_stat"] = _to_set_from_jsonish(entry.get("ev_yield")) if entry.get("ev_yield") is not None else set()

    # generation fields may not be present
    parsed["generation_first_introduced"] = _to_set_from_single(entry.get("generation")) if entry.get("generation") else set()
    parsed["generations_present"] = _to_set_from_jsonish(entry.get("generations")) or set()

    # evolution stage not parsed; leave empty set
    parsed["evolution_stage"] = set()

    return parsed


def load_pokemon() -> List[Dict[str, Any]]:
    path = pokemon_csv_path()
    if not path.exists():
        print(f"Could not find pokedex.json at: {path}")
        sys.exit(1)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # data is expected to be a mapping of keys -> pokemon objects
    rows: List[Dict[str, Any]] = []
    if isinstance(data, dict):
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            rows.append(parse_row(entry))
    elif isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                rows.append(parse_row(entry))
    return rows


def build_name_index(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = row.get("name_normalized", "")
        if key:
            index[key] = row
    return index


def select_secret_and_attrs(rows: Sequence[Dict[str, Any]], rng: random.Random) -> Tuple[Dict[str, Any], List[str]]:
    secret = rng.choice(rows)

    available_attrs: List[str] = []
    for key in NUMERIC_ATTRS:
        if secret.get(key) is not None:
            available_attrs.append(key)
    for key in CATEGORY_ATTRS:
        if secret.get(key) is not None:
            available_attrs.append(key)

    # Ensure we have at least 5 attributes; if not, broaden by allowing attributes even if None
    if len(available_attrs) < 5:
        available_attrs = list(set(NUMERIC_ATTRS + CATEGORY_ATTRS))

    rng.shuffle(available_attrs)
    chosen = available_attrs[:5]
    return secret, chosen


def compare_numeric(guess_val: Optional[float], secret_val: Optional[float]) -> str:
    if guess_val is None or secret_val is None:
        return "unknown"
    if abs(guess_val - secret_val) < 1e-9:
        return "equal"
    return "higher" if secret_val > guess_val else "lower"


def compare_category(guess_set: Optional[Set[str]], secret_set: Optional[Set[str]]) -> str:
    if guess_set is None or secret_set is None:
        return "unknown"
    if guess_set == secret_set:
        return "blue"
    if len(guess_set.intersection(secret_set)) > 0:
        return "yellow"
    return "red"


def format_attr_name(attr_key: str) -> str:
    return FRIENDLY_NAMES.get(attr_key, attr_key)


def get_attr_display(attr_key: str, row: Dict[str, Any]) -> str:
    """Return a human-readable string for an attribute value on a row."""
    if row is None:
        return "N/A"
    if attr_key in NUMERIC_ATTRS:
        val = row.get(attr_key)
        return str(int(val)) if isinstance(val, float) and val.is_integer() else (str(val) if val is not None else "N/A")
    # category: show comma-separated
    val_set = row.get(attr_key)
    if val_set is None:
        return "N/A"
    if isinstance(val_set, (set, list, tuple)):
        items = sorted([str(i) for i in val_set if str(i).strip() != ""])
        return ", ".join(items) if items else "N/A"
    return str(val_set)


def describe_secret_subset(secret: Dict[str, Any], attrs: Sequence[str]) -> str:
    parts: List[str] = []
    for key in attrs:
        if key in NUMERIC_ATTRS:
            parts.append(f"{format_attr_name(key)}: ?")
        else:
            # category set hidden; just mark as ? to avoid revealing
            parts.append(f"{format_attr_name(key)}: ?")
    return ", ".join(parts)


def game_loop(rows: List[Dict[str, Any]]) -> None:
    rng = random.SystemRandom()
    secret, attrs = select_secret_and_attrs(rows, rng)
    name_index = build_name_index(rows)

    print("Welcome to Pokedle!")
    print("I have selected a secret Pokémon and 5 attributes.")
    print("Attributes to compare:")
    for key in attrs:
        print(f" - {format_attr_name(key)}")
    print("Type a Pokémon name to guess (or 'quit' to exit).")
    # Uncomment to debug: print(secret.get("name"))

    # Keep a running history of guesses and their per-attribute results
    # history_rows: list of tuples (guess_name, [result_for_attr1, result_for_attr2, ...])
    history_rows: List[Tuple[str, List[str]]] = []

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return

        if user_input.lower() in {"q", "quit", "exit"}:
            print("Goodbye!")
            return

        guess_row = name_index.get(user_input.lower())
        if guess_row is None:
            print("Unknown Pokémon name. Please try again.")
            continue

        if guess_row.get("name") == secret.get("name"):
            print(f"Correct! The secret Pokémon was {secret.get('name')}.")
            return

        # Compute per-attribute results for this guess
        results_for_guess: List[str] = []
        for key in attrs:
            if key in NUMERIC_ATTRS:
                cell = compare_numeric(guess_row.get(key), secret.get(key))
            else:
                cell = compare_category(guess_row.get(key), secret.get(key))
            results_for_guess.append(cell)

        history_rows.append((guess_row.get("name", "<unknown>"), results_for_guess))

        # Build running table where columns are attributes and rows are guesses
        column_headers = ["Guess"] + [format_attr_name(k) for k in attrs]

        # Compute column widths based on headers and all history rows
        column_widths: List[int] = [len(h) for h in column_headers]
        for guess_name, results in history_rows:
            if len(column_widths) > 0:
                column_widths[0] = max(column_widths[0], len(str(guess_name)))
            for i, cell in enumerate(results, start=1):
                column_widths[i] = max(column_widths[i], len(str(cell)))

        # Print header
        header_line = " | ".join(h.ljust(column_widths[i]) for i, h in enumerate(column_headers))
        separator_line = "-+-".join("-" * w for w in column_widths)
        print("Not quite. Comparison so far:")
        print(header_line)
        print(separator_line)

        # Print each guess row
        for guess_name, results in history_rows:
            row_cells = [str(guess_name).ljust(column_widths[0])] + [str(results[i]).ljust(column_widths[i + 1]) for i in range(len(results))]
            print(" | ".join(row_cells))


def main() -> None:
    rows = load_pokemon()
    if not rows:
        print("No Pokémon data found.")
        sys.exit(1)
    game_loop(rows)


if __name__ == "__main__":
    main()


# --- Discord bot integration -------------------------------------------------
# This section exposes the game as a bot command. It requires discord.py v2 and
# the Message Content intent (to read guesses typed in the thread). The cog
# registers a `!pokedle` text command that starts a new thread and posts an
# editable embed which the bot updates as the player guesses.

try:
    import asyncio
    import discord
    from discord.ext import commands

    class PokedleSession:
        def __init__(self, bot: commands.Bot, channel: discord.abc.Messageable, player: discord.User):
            self.bot = bot
            self.channel = channel
            self.player = player
            self.rows = load_pokemon()
            self.name_index = build_name_index(self.rows)
            self.rng = random.SystemRandom()
            self.secret, self.attrs = select_secret_and_attrs(self.rows, self.rng)
            self.history: List[Tuple[str, List[str]]] = []

        def _render_table(self) -> Tuple[str, str]:
            """Return (names_column, results_column) strings for embed fields.

            names_column: bolded guess names, one per line.
            results_column: header row (attributes) then emoji rows aligned in monospace.
            """
            attr_names = [format_attr_name(k) for k in self.attrs]
            # compute column widths based on attribute display names
            col_widths = [max(1, len(n)) for n in attr_names]

            # header cells in monospace inline code
            header_cells = [f"`{attr_names[i].ljust(col_widths[i])}`" for i in range(len(attr_names))]
            header_line = " | ".join(header_cells)

            if not self.history:
                names_col = "(no guesses yet)"
                results_col = header_line
                return names_col, results_col

            names_lines: List[str] = []
            results_lines: List[str] = [header_line]
            for guess_name, results in self.history:
                names_lines.append(f"**{guess_name}**")
                emojis = [self._result_to_emoji(k, results[i]) for i, k in enumerate(self.attrs)]
                emoji_cells = [f"`{emojis[i].center(col_widths[i]-1)}`" for i in range(len(emojis))]
                results_lines.append(" | ".join(emoji_cells))

            names_col = "\n".join(names_lines)
            results_col = "\n".join(results_lines)
            return names_col, results_col

        def _result_to_emoji(self, key: str, result: str) -> str:
            """Map a comparison result to an emoji string."""
            # Numeric: result is 'equal'|'higher'|'lower'|'unknown'
            if key in NUMERIC_ATTRS:
                if result == "equal":
                    return "🟦"  # exact
                if result == "higher":
                    return "🔼"  # secret is higher than guess
                if result == "lower":
                    return "🔽"  # secret is lower than guess
                return "❔"
            # Category: 'blue' exact, 'yellow' partial, 'red' none
            if result == "blue":
                return "🟦"
            if result == "yellow":
                return "🟨"
            if result == "red":
                return "🟥"
            return "❔"

        def _build_embed(self) -> discord.Embed:
            title = f"Pokedle — {self.player.display_name}"
            embed = discord.Embed(title=title, colour=discord.Colour.blurple())
            embed.add_field(name="Attributes", value="\n".join(f"• {format_attr_name(k)}" for k in self.attrs), inline=False)
            names_col, results_col = self._render_table()
            embed.add_field(name="Guesses", value='Attributes' + '\n' + names_col, inline=True)
            embed.add_field(name="Results", value=results_col, inline=True)
            embed.set_footer(text="Type a Pokémon name in this thread to guess. Type 'quit' to end.")
            return embed

        async def run(self, thread: discord.Thread, bot_message: discord.Message) -> None:
            # The thread is already created; bot_message is the first message in it
            def check(m: discord.Message) -> bool:
                return m.author == self.player and m.channel.id == thread.id and not m.author.bot

            # initial edit to show empty state
            await bot_message.edit(embed=self._build_embed())

            while True:
                try:
                    msg: discord.Message = await self.bot.wait_for('message', check=check, timeout=60 * 15)
                except asyncio.TimeoutError:
                    # timeout: update embed and close
                    embed = self._build_embed()
                    embed.colour = discord.Colour.dark_grey()
                    embed.set_footer(text="Game timed out (15m).")
                    await bot_message.edit(embed=embed)
                    return

                content = msg.content.strip()
                if content.lower() in {"q", "quit", "exit"}:
                    await thread.send(f"{self.player.mention} ended the game.")
                    embed = self._build_embed()
                    embed.colour = discord.Colour.dark_grey()
                    embed.set_footer(text="Game ended by player.")
                    await bot_message.edit(embed=embed)
                    return

                guess_row = self.name_index.get(content.lower())
                if guess_row is None:
                    await thread.send(f"Unknown Pokémon: `{content}`. Try again.")
                    continue

                if guess_row.get("name") == self.secret.get("name"):
                    # correct — reveal and finish
                    await thread.send(f"Correct! {self.player.mention} guessed the secret Pokémon: **{self.secret.get('name')}** 🎉")
                    # add final row with all 'equal'
                    results = ["equal" if k in NUMERIC_ATTRS else "blue" for k in self.attrs]
                    self.history.append((guess_row.get("name"), results))
                    embed = self._build_embed()
                    embed.colour = discord.Colour.green()
                    embed.set_footer(text="Solved!")
                    await bot_message.edit(embed=embed)
                    return

                # compute per-attribute results
                results_for_guess: List[str] = []
                for key in self.attrs:
                    if key in NUMERIC_ATTRS:
                        cell = compare_numeric(guess_row.get(key), self.secret.get(key))
                    else:
                        cell = compare_category(guess_row.get(key), self.secret.get(key))
                    results_for_guess.append(cell)

                self.history.append((guess_row.get("name", "<unknown>"), results_for_guess))
                # update embed
                await bot_message.edit(embed=self._build_embed())
                # ack
                await msg.add_reaction("✅")

    class PokedleCog(commands.Cog):
        def __init__(self, bot: commands.Bot):
            self.bot = bot

        @commands.command(name="pokedle")
        async def pokedle_command(self, ctx: commands.Context) -> None:
            """Start a Pokedle game in a new thread. The invoking user will be the player."""
            # create a thread in the current channel
            starter = await ctx.send(f"{ctx.author.mention} is starting a Pokedle game... creating thread...")
            thread = await starter.create_thread(name=f"Pokedle — {ctx.author.display_name}", auto_archive_duration=60)
            # send the editable embed message as the first message in the thread
            session = PokedleSession(self.bot, ctx.channel, ctx.author)
            bot_msg = await thread.send("Preparing game...")
            # run session
            await session.run(thread, bot_msg)

    async def setup(bot: commands.Bot):
        await bot.add_cog(PokedleCog(bot))

except Exception:
    # If discord.py isn't available, skip bot integration silently
    pass


