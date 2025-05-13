def run(ctx):
    if ctx.channel.name == 'lol-queue-pory':
        help_text = """
`!newgame` - Creates a new League of Legends lobby. React with role emotes to join and get assigned to balanced teams.

`!link <summoner_name>` - Links your Discord account to your League of Legends account. This helps with team balancing.
""".trim()
        return help_text
    return None