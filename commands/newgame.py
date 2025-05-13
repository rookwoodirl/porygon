import discord
from discord.ext import commands
import asyncio
import os
import random
import traceback
import sys
import json

ROLE_EMOTES = ['TOP', 'JGL', 'MID', 'BOT', 'SUP']
TEAM_EMOTES = ['🅰️', '🅱️']  # These are default Unicode emojis
SUMMONERS_FILE = 'data/summoners.json'

def load_summoners():
    """Load the summoners mapping from the JSON file."""
    if os.path.exists(SUMMONERS_FILE):
        with open(SUMMONERS_FILE, 'r') as f:
            return json.load(f)
    return {}

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
        self.rank = None
        self.top_champs = []

        # Load summoner data if available
        try:
            with open(os.path.join('data', 'summoners.json'), 'r') as f:
                summoners = json.load(f)
                if discord_name in summoners:
                    summoner_data = summoners[discord_name]
                    if 'rank' in summoner_data:
                        self.rank = summoner_data['rank']
                    if 'top_champs' in summoner_data:
                        self.top_champs = summoner_data['top_champs']
        except (FileNotFoundError, json.JSONDecodeError):
            pass  # Handle case where file doesn't exist or is invalid

class Match:
    def __init__(self, emotes):
        self.emotes = emotes
        self.preferred_roles = {role: [] for role in ROLE_EMOTES}
        self.players = {team: {role: None for role in ROLE_EMOTES} for team in TEAM_EMOTES}
        self.player_preferences = {}  # discord_name -> Player object
        self.message = None

    def roles_dfs(self):
        print('Starting DFS for role assignment...')
        used_players = set()  # Track all used players across both teams
        
        def dfs(team, role_index):
            if role_index >= len(ROLE_EMOTES):
                print(f'DFS completed for team {team} with used players: {used_players}')
                return True
            
            role = ROLE_EMOTES[role_index]
            print(f'Processing role {role} for team {team}')
            # If no players want this role, skip it
            if not self.preferred_roles[role]:
                print(f'No players want role {role}, skipping')
                return dfs(team, role_index + 1)
            
            print(f'Players wanting role {role}: {self.preferred_roles[role]}')
            for player_name in self.preferred_roles[role]:
                if player_name in used_players:
                    print(f'Player {player_name} already used, skipping')
                    continue
                
                print(f'Assigning {player_name} to {team} {role}')
                self.players[team][role] = player_name
                used_players.add(player_name)
                
                if dfs(team, role_index + 1):
                    return True
                
                print(f'Backtracking: removing {player_name} from {team} {role}')
                self.players[team][role] = None
                used_players.remove(player_name)
            
            # If we couldn't fill this role, try continuing with the next role
            print(f'Could not fill role {role} for team {team}, trying next role')
            return dfs(team, role_index + 1)

        # Reset players dictionary
        self.players = {team: {role: None for role in ROLE_EMOTES} for team in TEAM_EMOTES}
        
        # Try to fill roles for both teams
        for team in TEAM_EMOTES:
            print(f'\nStarting DFS for team {team}')
            print(f'Current players state before DFS: {self.players}')
            if not dfs(team, 0):
                print(f'Warning: Could not find valid assignment for team {team}')
            print(f'Team {team} roles assigned. Final state: {self.players}')

    def description(self):
        PAD = max([len(player.discord_name) for player in self.player_preferences.values()])
        description = []
        # List all queued users and their role preferences
        queued_players = []
        if self.player_preferences:
            for player in self.player_preferences.values():
                roles = ''.join([
                    f'{self.emotes.get(role, ":" + role + ":")}' for role in sorted(player.preferred_roles)
                ]) if player.preferred_roles else 'None'
                
                # Get rank info if available
                rank_info = ""
                if player.rank:
                    rank_info = f" [{player.rank}]"
                
                # Get top champs if available
                champs_info = ""
                if player.top_champs:
                    champs_info = f" | {', '.join(player.top_champs)}"
                
                queued_players.append(f'{player.discord_name}{rank_info}{champs_info} : _( {roles} )_')
            queued_players.append("")

        # Team/role assignments
        lane_matchups = []
        for role in ROLE_EMOTES:
            red_player = self.players[TEAM_EMOTES[0]][role] or "Empty"
            blue_player = self.players[TEAM_EMOTES[1]][role] or "Empty"
            emoji = self.emotes.get(role, role)
            # Pad names to PAD chars for rough alignment
            left = f"{red_player:<{PAD}.{PAD}}"
            right = f"{blue_player:<{PAD}.{PAD}}"
            lane_matchups.append(f"`{left}` {emoji} `{right}`\t@{red_player} vs. @{blue_player}")

        description.append('**Queued Players:**')
        description.append('\n'.join(queued_players))
        description.append('**Lane Matchups:**')
        description.append('\n'.join(lane_matchups))
        
        return '\n'.join(description)

    def has_enough_players(self):
        """Check if we have enough 'ready' players (with both a role and a team) and role coverage to start team assignment."""
        ready_players = [p for p in self.player_preferences.values() if p.preferred_roles]
        if len(ready_players) < 10:
            return False
        # Check if we have at least one ready player for each role
        for role in ROLE_EMOTES:
            if not any(role in p.preferred_roles for p in ready_players):
                return False
        return True

    async def on_react(self, reaction, user):
        # Get emoji name safely
        if hasattr(reaction.emoji, 'name'):
            emoji_name = reaction.emoji.name
        else:
            emoji_name = str(reaction.emoji)
        
        discord_tag = str(user)  # Use full Discord name including discriminator
        print(f"Reaction from {discord_tag}: {emoji_name}")  # Debug print
        
        if emoji_name not in ROLE_EMOTES:
            return

        if discord_tag not in self.player_preferences:
            self.player_preferences[discord_tag] = Player(discord_tag)
            print(f"Created new player: {discord_tag}")  # Debug print

        player = self.player_preferences[discord_tag]
        
        if emoji_name in ROLE_EMOTES:
            player.preferred_roles.add(emoji_name)
            if emoji_name not in self.preferred_roles[emoji_name]:
                self.preferred_roles[emoji_name].append(discord_tag)
                print(f"Added {discord_tag} to {emoji_name} role preferences")  # Debug print

        # Debug: print current player preferences and preferred_roles
        print("Current player_preferences:")
        for k, v in self.player_preferences.items():
            print(f"  {k}: roles={v.preferred_roles}")
        print("Current preferred_roles:")
        for role, users in self.preferred_roles.items():
            print(f"  {role}: {users}")

        # Update the message with current state
        await self.message.edit(content=self.description())
        print(f"Current players: {len(self.player_preferences)}")  # Debug print

        # Always clear assignments and re-run DFS if enough players and roles
        if self.has_enough_players():
            print("Starting role assignment...")  # Debug print
            print("Players before assignment:", self.players)
            self.players = {team: {role: None for role in ROLE_EMOTES} for team in TEAM_EMOTES}
            self.roles_dfs()
            print("Players after assignment:", self.players)
            await self.message.edit(content=self.description())
            print("Role assignment complete")  # Debug print

async def simulate_users(match):
    """Simulate 9 users with hardcoded preferences."""
    # Each tuple: (username, [roles])
    user_data = [
        ("User1",  random.sample(ROLE_EMOTES, 3)),
        ("User2",  random.sample(ROLE_EMOTES, 3)),
        ("User3",  random.sample(ROLE_EMOTES, 3)),
        ("User4",  random.sample(ROLE_EMOTES, 3)),
        ("User5",  random.sample(ROLE_EMOTES, 3)),
        ("User6",  random.sample(ROLE_EMOTES, 3)),
        ("User7",  random.sample(ROLE_EMOTES, 3)),
        ("User8",  random.sample(ROLE_EMOTES, 3)),
        ("User9",  random.sample(ROLE_EMOTES, 3)),
    ]
    
    # Directly update the data structures
    for user_name, roles in user_data:
        match.player_preferences[user_name] = Player(user_name)
        player = match.player_preferences[user_name]
        player.preferred_roles = set(roles)
        
        # Update preferred_roles lists
        for role in roles:
            if role not in match.preferred_roles[role]:
                match.preferred_roles[role].append(user_name)
        
        print(f"Simulated {user_name} with roles: {roles}")
    
    # Update the message once after all simulations
    await match.message.edit(content=match.description())
    
    # Run DFS if we have enough players
    if match.has_enough_players():
        match.roles_dfs()
        await match.message.edit(content=match.description())

async def new_game(ctx):
    """
    !newgame 
    Posts to #lol-queue. Creates channel if it does not exist.
    Reacts to itself with each of ROLE_EMOTES and TEAM_EMOTES, to start the poll
    Distributes players to Team A and Team B, giving players one of their preferred roles
    """
    try:
        # Ensure all required emotes exist
        emotes = await ensure_emotes_exist(ctx.guild)

        # Find or create the lol-queue channel
        channel = discord.utils.get(ctx.guild.channels, name='lol-queue')
        if not channel:
            channel = await ctx.guild.create_text_channel('lol-queue', category=ctx.channel.category)

        # Create a new match
        match = Match(emotes)
        
        # Send the initial message
        message = await channel.send("League of Legends Lobby\nReact with roles to join!")
        match.message = message

        # Add reactions for roles
        for emote_name in ROLE_EMOTES:
            emoji = emotes.get(emote_name, emote_name)
            await message.add_reaction(emoji)

        # Simulate users
        await simulate_users(match)

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
            except Exception as e:
                print("Error processing reaction:", file=sys.stderr)
                print("Error type:", type(e).__name__, file=sys.stderr)
                print("Error message:", str(e), file=sys.stderr)
                print("Stack trace:", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                await message.edit(content=f"Error processing reaction: {str(e)}")
                continue

    except Exception as e:
        print("Error in new_game:", file=sys.stderr)
        print("Error type:", type(e).__name__, file=sys.stderr)
        print("Error message:", str(e), file=sys.stderr)
        print("Stack trace:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if 'message' in locals():
            await message.edit(content=f"Error in game setup: {str(e)}")
        raise

async def run(ctx):
    try:
        return await new_game(ctx)
    except Exception as e:
        print("Error in run:", file=sys.stderr)
        print("Error type:", type(e).__name__, file=sys.stderr)
        print("Error message:", str(e), file=sys.stderr)
        print("Stack trace:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise