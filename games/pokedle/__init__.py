from __future__ import annotations

import json
import random
from ast import literal_eval
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, TYPE_CHECKING

from .. import PuzzleGame

try:
    import discord  # type: ignore
    from discord.ext import commands  # type: ignore
except Exception:  # pragma: no cover - optional at import time
    discord = None  # type: ignore
    commands = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover
    import discord as _discord
    from discord.ext import commands as _commands


# -------------------- data mapping and helpers --------------------

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
    "national_dex_number": "National Dex #",
    "base_hp": "HP",
    "base_attack": "Atk",
    "base_defense": "Def",
    "base_sp_attack": "Sp. Atk",
    "base_sp_defense": "Sp. Def",
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
    # package file sits at repo/games/pokedle/__init__.py -> go up two levels to repo
    return Path(__file__).resolve().parents[2]


def pokedex_path() -> Path:
    return project_root() / "games" / "pokedle" / "pokedex.json"


def _to_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        try:
            text = str(value).strip()
            return float(text) if text else None
        except Exception:
            return None


def _to_set_from_jsonish(value: Any) -> Set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip() != ""}
    text = str(value).strip()
    if text == "":
        return set()
    try:
        parsed = literal_eval(text)
        if isinstance(parsed, (list, tuple, set)):
            return {str(item).strip() for item in parsed if str(item).strip() != ""}
    except Exception:
        pass
    return {text}


def _to_set_from_single(value: Any) -> Set[str]:
    if value is None:
        return set()
    text = str(value).strip()
    return {text} if text else set()


def parse_row(entry: Dict[str, Any]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    parsed["name"] = entry.get("name")
    parsed["name_normalized"] = (entry.get("name") or "").strip().lower()

    parsed["national_dex_number"] = _to_number(entry.get("national_dex"))
    bs = entry.get("base_stats") or {}
    parsed["base_hp"] = _to_number(bs.get("hp"))
    parsed["base_attack"] = _to_number(bs.get("attack"))
    parsed["base_defense"] = _to_number(bs.get("defense"))
    parsed["base_sp_attack"] = _to_number(bs.get("sp_attack"))
    parsed["base_sp_defense"] = _to_number(bs.get("sp_defense"))
    parsed["base_speed"] = _to_number(bs.get("speed"))
    parsed["height_m"] = _to_number(entry.get("height_m"))
    parsed["weight_kg"] = _to_number(entry.get("weight_kg"))

    types = [t for t in (entry.get("types") or []) if t and str(t).strip().lower() != "unknown"]
    parsed["primary_type"] = {types[0]} if len(types) >= 1 else set()
    parsed["secondary_type"] = {types[1]} if len(types) >= 2 else set()

    parsed["egg_groups"] = _to_set_from_jsonish(entry.get("egg_groups"))
    parsed["ev_yield_stat"] = _to_set_from_jsonish(entry.get("ev_yield")) if entry.get("ev_yield") is not None else set()
    parsed["generation_first_introduced"] = _to_set_from_single(entry.get("generation")) if entry.get("generation") else set()
    parsed["generations_present"] = _to_set_from_jsonish(entry.get("generations"))
    parsed["evolution_stage"] = set()

    return parsed


def load_pokemon() -> List[Dict[str, Any]]:
    path = pokedex_path()
    if not path.exists():
        raise FileNotFoundError(f"Could not find pokedex.json at: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    rows: List[Dict[str, Any]] = []
    if isinstance(data, dict):
        for entry in data.values():
            if isinstance(entry, dict):
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
    available: List[str] = []
    for key in NUMERIC_ATTRS:
        if secret.get(key) is not None:
            available.append(key)
    for key in CATEGORY_ATTRS:
        if secret.get(key) is not None:
            available.append(key)
    if len(available) < 5:
        available = list(set(NUMERIC_ATTRS + CATEGORY_ATTRS))
    rng.shuffle(available)
    return secret, available[:5]


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


# -------------------- game implementation --------------------

class PokedleGame(PuzzleGame):
    def __init__(self, bot: "_commands.Bot", player: "_discord.User") -> None:
        super().__init__(bot, player)
        self.rows: List[Dict[str, Any]] = []
        self.name_index: Dict[str, Dict[str, Any]] = {}
        self.secret: Dict[str, Any] = {}
        self.attrs: List[str] = []
        self._embed_colour = (discord.Colour.blurple() if discord else None)  # type: ignore[attr-defined]

    async def setup(self, ctx: "_commands.Context") -> "_discord.Embed":
        self.rows = load_pokemon()
        self.name_index = build_name_index(self.rows)
        rng = random.SystemRandom()
        self.secret, self.attrs = select_secret_and_attrs(self.rows, rng)
        return self.build_embed()

    def _result_to_emoji(self, key: str, result: str) -> str:
        if key in NUMERIC_ATTRS:
            if result == "equal":
                return "🟦"
            if result == "higher":
                return "🔼"
            if result == "lower":
                return "🔽"
            return "❔"
        if result == "blue":
            return "🟦"
        if result == "yellow":
            return "🟨"
        if result == "red":
            return "🟥"
        return "❔"

    def _render_columns(self) -> Tuple[str, str]:
        attr_names = [format_attr_name(k) for k in self.attrs]
        col_widths = [max(1, len(n)) for n in attr_names]
        header_cells = [f"`{attr_names[i].ljust(col_widths[i])}`" for i in range(len(attr_names))]
        header_line = "\u2003".join(header_cells)

        if not self.history:
            return "(no guesses yet)", header_line

        names_lines: List[str] = []
        results_lines: List[str] = [header_line]
        for guess_name, results in self.history:
            names_lines.append(f"**{guess_name}**")
            emojis = [self._result_to_emoji(k, results[i]) for i, k in enumerate(self.attrs)]
            emoji_cells = [f"`{emojis[i].center(col_widths[i])}`" for i in range(len(emojis))]
            results_lines.append(" | ".join(emoji_cells))

        return "\n".join(names_lines), "\n".join(results_lines)

    def build_embed(self) -> "_discord.Embed":
        title = f"Pokedle — {getattr(self.player, 'display_name', 'Player')}"
        embed = discord.Embed(title=title, colour=self._embed_colour)  # type: ignore[arg-type]
        embed.add_field(name="Attributes", value="\n".join(f"• {format_attr_name(k)}" for k in self.attrs), inline=False)
        names_col, results_col = self._render_columns()
        embed.add_field(name="Guesses", value="--\n"+names_col, inline=True)
        embed.add_field(name="Results", value=results_col, inline=True)
        embed.set_footer(text="Type a Pokémon name in this thread to guess. Type 'quit' to end.")
        return embed

    async def handle_user_message(self, message: "_discord.Message") -> Tuple[bool, Optional[str]]:
        content = (message.content or "").strip()
        if content.lower() in {"q", "quit", "exit"}:
            self._embed_colour = (discord.Colour.dark_grey() if discord else None)  # type: ignore[attr-defined]
            return True, f"{message.author.mention} ended the game."

        guess_row = self.name_index.get(content.lower())
        if guess_row is None:
            return False, f"Unknown Pokémon: `{content}`. Try again."

        if guess_row.get("name") == self.secret.get("name"):
            results = ["equal" if k in NUMERIC_ATTRS else "blue" for k in self.attrs]
            self.add_history(guess_row.get("name", "<unknown>"), results)
            self._embed_colour = (discord.Colour.green() if discord else None)  # type: ignore[attr-defined]
            return True, f"Correct! {message.author.mention} guessed the secret Pokémon: **{self.secret.get('name')}** 🎉"

        # compute per-attribute results
        results_for_guess: List[str] = []
        for key in self.attrs:
            if key in NUMERIC_ATTRS:
                cell = compare_numeric(guess_row.get(key), self.secret.get(key))
            else:
                cell = compare_category(guess_row.get(key), self.secret.get(key))
            results_for_guess.append(cell)
        self.add_history(guess_row.get("name", "<unknown>"), results_for_guess)
        return False, None


class PokedleCog(commands.Cog):  # type: ignore[misc]
    def __init__(self, bot: "_commands.Bot") -> None:
        self.bot = bot

    @commands.command(name="pokedle")  # type: ignore[misc]
    async def pokedle_command(self, ctx: "_commands.Context") -> None:
        try:
            starter = await ctx.send(f"{ctx.author.mention} is starting a Pokedle game... creating thread...")
            thread = await starter.create_thread(name=f"Pokedle — {ctx.author.display_name}", auto_archive_duration=60)
            bot_msg = await thread.send("Preparing game...")
            game = PokedleGame(self.bot, ctx.author)
            await game.setup(ctx)
            # show initial state, then run loop
            await bot_msg.edit(embed=game.build_embed())
            await game.run_in_thread(thread, bot_msg)
        except Exception as e:
            await ctx.send(f"Failed to start Pokedle: {e}")


async def setup(bot: "_commands.Bot") -> None:
    await bot.add_cog(PokedleCog(bot))


