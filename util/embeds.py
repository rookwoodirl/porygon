import random
import discord


def embed_for_text(text: str, title: str | None = None) -> discord.Embed:
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


__all__ = ["embed_for_text"]


