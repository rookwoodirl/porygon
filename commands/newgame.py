import discord
from discord.ext import commands
import asyncio
import os

ROLE_EMOTES = ['TOP', 'JGL', 'MID', 'BOT', 'SUP']
TEAM_EMOTES = ['a', 'b']  # These are default Unicode emojis

async def ensure_emotes_exist(guild):
    """Ensure all required emotes exist in the server, create them if they don't."""
    existing_emotes = {str(e.name): e for e in await guild.fetch_emojis()}
    emotes_dir = os.path.join('commands', 'lol_emotes')
    
    # Ensure role emotes exist
    for role in ROLE_EMOTES:
        if role not in existing_emotes:
            emote_path = os.path.join(emotes_dir, f'{role}.png')
            if os.path.exists(emote_path):
                with open(emote_path, 'rb') as f:
                    emoji_bytes = f.read()
                    await guild.create_custom_emoji(name=role, image=emoji_bytes)
                    print(f"Created emote: {role}")

    # Get all emotes including custom ones
    emotes = {str(e.name): e for e in await guild.fetch_emojis()}
    # Add default emojis for teams
    emotes.update({'a': '🅰️', 'b': '🅱️'})
    return emotes

class Player:
    def __init__(self, discord_name):
        self.discord_name = discord_name
        self.preferred_roles = set()
        self.preferred_teams = set()

class Match:
    def __init__(self, emotes):
        self.emotes = emotes
        self.preferred_roles = {role: [] for role in ROLE_EMOTES}
        self.players = {team: {role: None for role in ROLE_EMOTES} for team in TEAM_EMOTES}
        self.player_preferences = {}  # discord_name -> Player object
        self.message = None

    def roles_dfs(self):
        print('Nice!')
        def dfs(team, role_index, used_players):
            if role_index >= len(ROLE_EMOTES):
                return True
            
            role = ROLE_EMOTES[role_index]
            # If no players want this role, skip it
            if not self.preferred_roles[role]:
                return dfs(team, role_index + 1, used_players)
            
            for player_name in self.preferred_roles[role]:
                if player_name in used_players:
                    continue
                
                player = self.player_preferences[player_name]
                if team in player.preferred_teams:
                    self.players[team][role] = player_name
                    used_players.add(player_name)
                    
                    if dfs(team, role_index + 1, used_players):
                        return True
                    
                    self.players[team][role] = None
                    used_players.remove(player_name)
            
            # If we couldn't fill this role, try continuing with the next role
            return dfs(team, role_index + 1, used_players)

        # Try to fill roles for both teams
        for team in TEAM_EMOTES:
            dfs(team, 0, set())
            print(f"Team {team} roles assigned")  # Debug print

    def description(self):
        lines = []
        for role in ROLE_EMOTES:
            red_player = self.players[TEAM_EMOTES[0]][role] or "Empty"
            blue_player = self.players[TEAM_EMOTES[1]][role] or "Empty"
            emoji = self.emotes.get(role, role)
            lines.append(f'{red_player} {emoji} {blue_player}')
        return '\n'.join(lines)

    def has_enough_players(self):
        """Check if we have enough players and role preferences to start team assignment."""
        if len(self.player_preferences) < 10:
            return False
        
        # Check if we have at least one player for each role
        for role in ROLE_EMOTES:
            if not self.preferred_roles[role]:
                return False
        
        return True

    async def on_react(self, reaction, user):
        emoji_name = str(reaction.emoji.name) if hasattr(reaction.emoji, 'name') else str(reaction.emoji)
        print(f"Reaction from {user.name}: {emoji_name}")  # Debug print
        
        if emoji_name not in ROLE_EMOTES + TEAM_EMOTES:
            return

        if user.name not in self.player_preferences:
            self.player_preferences[user.name] = Player(user.name)
            print(f"Created new player: {user.name}")  # Debug print

        player = self.player_preferences[user.name]
        
        if emoji_name in ROLE_EMOTES:
            player.preferred_roles.add(emoji_name)
            if emoji_name not in self.preferred_roles[emoji_name]:
                self.preferred_roles[emoji_name].append(user.name)
                print(f"Added {user.name} to {emoji_name} role preferences")  # Debug print
        elif emoji_name in TEAM_EMOTES:
            player.preferred_teams.add(emoji_name)
            print(f"Added {user.name} to {emoji_name} team preferences")  # Debug print

        # Update the message with current state
        await self.message.edit(content=self.description())
        print(f"Current players: {len(self.player_preferences)}")  # Debug print

        # Only run DFS if we have enough players and role preferences
        if self.has_enough_players():
            print("Starting role assignment...")  # Debug print
            self.roles_dfs()
            await self.message.edit(content=self.description())
            print("Role assignment complete")  # Debug print

async def new_game(ctx):
    """
    !newgame 
    Posts to #lol-queue. Creates channel if it does not exist.
    Reacts to itself with each of ROLE_EMOTES and TEAM_EMOTES, to start the poll
    Distributes players to Team A and Team B, giving players one of their preferred roles
    """
    # Ensure all required emotes exist
    emotes = await ensure_emotes_exist(ctx.guild)

    # Find or create the lol-queue channel
    channel = discord.utils.get(ctx.guild.channels, name='lol-queue')
    if not channel:
        channel = await ctx.guild.create_text_channel('lol-queue', category=ctx.channel.category)

    # Create a new match
    match = Match(emotes)
    
    # Send the initial message
    message = await channel.send("League of Legends Lobby\nReact with roles and teams to join!")
    match.message = message

    # Add reactions for roles and teams
    for emote_name in ROLE_EMOTES + TEAM_EMOTES:
        emoji = emotes.get(emote_name, emote_name)
        await message.add_reaction(emoji)

    # Set up reaction listener
    def check(reaction, user):
        return reaction.message.id == message.id and not user.bot

    while True:
        try:
            reaction, user = await ctx.bot.wait_for('reaction_add', timeout=3600, check=check)
            await match.on_react(reaction, user)
        except asyncio.TimeoutError:
            await message.edit(content="Lobby timed out after 1 hour")
            break

async def run(ctx):
    return await new_game(ctx)