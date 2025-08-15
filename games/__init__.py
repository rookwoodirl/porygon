from __future__ import annotations

from typing import List, Optional, Tuple, TYPE_CHECKING

try:
    import discord  # type: ignore
    from discord.ext import commands  # type: ignore
except Exception:  # pragma: no cover - optional at import time
    discord = None  # type: ignore
    commands = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover - for static type checkers only
    import discord as _discord
    from discord.ext import commands as _commands


class Game:
    """Base class for all games.

    Provides a minimal interface and shared state for games that may or may not
    integrate with Discord. Concrete games should subclass more specific base
    classes (e.g., GameThread) to leverage Discord helpers.
    """

    def __init__(self) -> None:
        self.is_finished: bool = False


class GameThread(Game):
    """Base class for Discord thread-based games.

    Subclasses should override:
    - async setup(ctx): initialize internal state and return initial embed
    - build_embed(): build and return the current discord.Embed snapshot
    - message_check(message): return True if a message should be consumed by the game
    - async handle_user_message(message): mutate state based on message and return a tuple
      (done: bool, ephemeral_reply: Optional[str])
    """

    def __init__(self, bot: "_commands.Bot", player: "_discord.User") -> None:
        super().__init__()
        self.bot = bot
        self.player = player
        self.timeout_seconds: float = 60 * 15

    async def setup(self, ctx: "_commands.Context") -> "_discord.Embed":  # pragma: no cover - to be overridden
        raise NotImplementedError

    def build_embed(self) -> "_discord.Embed":  # pragma: no cover - to be overridden
        raise NotImplementedError

    def message_check(self, message: "_discord.Message") -> bool:
        try:
            # Default gating: same author as player and same thread
            return (message.author == self.player) and hasattr(message.channel, "id")
        except Exception:
            return False

    async def handle_user_message(self, message: "_discord.Message") -> Tuple[bool, Optional[str]]:  # pragma: no cover
        raise NotImplementedError

    async def run_in_thread(self, thread: "_discord.Thread", bot_message: "_discord.Message") -> None:
        # Initial render
        await bot_message.edit(embed=self.build_embed())

        while not self.is_finished:
            try:
                msg: "_discord.Message" = await self.bot.wait_for(
                    "message",
                    check=lambda m: self.message_check(m) and getattr(m.channel, "id", None) == thread.id,
                    timeout=self.timeout_seconds,
                )
            except Exception:
                # timeout
                try:
                    embed = self.build_embed()
                    if discord:
                        embed.colour = discord.Colour.dark_grey()  # type: ignore[attr-defined]
                    embed.set_footer(text="Game timed out (15m).")
                    await bot_message.edit(embed=embed)
                except Exception:
                    pass
                self.is_finished = True
                return

            done, ephemeral = await self.handle_user_message(msg)
            try:
                await bot_message.edit(embed=self.build_embed())
            except Exception:
                pass
            if ephemeral:
                try:
                    await thread.send(ephemeral)
                except Exception:
                    pass
            if done:
                self.is_finished = True
                return


class PuzzleGame(GameThread):
    """Base class for guessing-style puzzle games with a running history.

    Provides utility for storing a history of guesses and rendering them. The
    exact evaluation logic and embed layout remain the responsibility of the
    concrete subclass.
    """

    def __init__(self, bot: "_commands.Bot", player: "_discord.User") -> None:
        super().__init__(bot, player)
        self.history: List[Tuple[str, List[str]]] = []

    def add_history(self, guess_name: str, result_cells: List[str]) -> None:
        self.history.append((guess_name, result_cells))