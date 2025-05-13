import discord
from discord.ext import commands
import asyncio
import os
import random
import traceback
import sys

ROLE_EMOTES = ['TOP', 'JGL', 'MID', 'BOT', 'SUP']
TEAM_EMOTES = ['🅰️', '🅱️']  # These are default Unicode emojis

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
        print('Starting DFS for role assignment...')
        
        def dfs(team, role_index, used_players):
            if role_index >= len(ROLE_EMOTES):
                print(f'DFS completed for team {team} with used players: {used_players}')
                return True
            
            role = ROLE_EMOTES[role_index]
            print(f'Processing role {role} for team {team}')
            
            # If no players want this role, skip it
            if not self.preferred_roles[role]:
                print(f'No players want role {role}, skipping')
                return dfs(team, role_index + 1, used_players)
            
            print(f'Players wanting role {role}: {self.preferred_roles[role]}')
            
            # Try each player who wants this role
            for player_name in self.preferred_roles[role]:
                if player_name in used_players:
                    print(f'Player {player_name} already used, skipping')
                    continue
                
                player = self.player_preferences[player_name]
                print(f'Checking player {player_name} for team {team}, preferred teams: {player.preferred_teams}')
                
                # If player has no team preference or prefers this team
                if not player.preferred_teams or team in player.preferred_teams:
                    print(f'Assigning {player_name} to {team} {role}')
                    self.players[team][role] = player_name
                    used_players.add(player_name)
                    
                    if dfs(team, role_index + 1, used_players):
                        return True
                    
                    print(f'Backtracking: removing {player_name} from {team} {role}')
                    self.players[team][role] = None
                    used_players.remove(player_name)
                else:
                    print(f'Player {player_name} does not prefer team {team}')
            
            # If we couldn't fill this role, try continuing with the next role
            print(f'Could not fill role {role} for team {team}, trying next role')
            return dfs(team, role_index + 1, used_players)

        # Reset players dictionary
        self.players = {team: {role: None for role in ROLE_EMOTES} for team in TEAM_EMOTES}
        
        # Try to fill roles for both teams
        for team in TEAM_EMOTES:
            print(f'\nStarting DFS for team {team}')
            print(f'Current players state before DFS: {self.players}')
            if not dfs(team, 0, set()):
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
                queued_players.append(f'{player.discord_name} : _( {roles} )_')
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
        ready_players = [p for p in self.player_preferences.values() if p.preferred_roles and p.preferred_teams]
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
        
        discord_tag = f"{getattr(user, 'name', str(user))}"
        print(f"Reaction from {discord_tag}: {emoji_name}")  # Debug print
        
        if emoji_name not in ROLE_EMOTES + TEAM_EMOTES:
            print(f"Invalid emoji: {emoji_name}")
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
        elif emoji_name in TEAM_EMOTES:
            print(f"Processing team preference for {discord_tag}: {emoji_name}")
            print(f"Current preferred_teams before: {player.preferred_teams}")
            player.preferred_teams.add(emoji_name)
            print(f"Current preferred_teams after: {player.preferred_teams}")
            print(f"Added {discord_tag} to {emoji_name} team preferences")  # Debug print

        # Debug: print current player preferences and preferred_roles
        print("\nCurrent player_preferences:")
        for k, v in self.player_preferences.items():
            print(f"  {k}: roles={v.preferred_roles}, teams={v.preferred_teams}")
        print("\nCurrent preferred_roles:")
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
    """Simulate 9 users with hardcoded preferences, each reacting with both a role and a team, leaving Team B SUPP open for a real user."""
    # Each tuple: (username, [roles], [teams])
    user_data = [
        ("User1",  random.sample(ROLE_EMOTES, 3), [TEAM_EMOTES[0]]),
        ("User2",  random.sample(ROLE_EMOTES, 3), [TEAM_EMOTES[0]]),
        ("User3",  random.sample(ROLE_EMOTES, 3), [TEAM_EMOTES[0]]),
        ("User4",  random.sample(ROLE_EMOTES, 3), [TEAM_EMOTES[0]]),
        ("User5",  random.sample(ROLE_EMOTES, 3), [TEAM_EMOTES[0]]),
        ("User6",  random.sample(ROLE_EMOTES, 3), [TEAM_EMOTES[1]]),
        ("User7",  random.sample(ROLE_EMOTES, 3), [TEAM_EMOTES[1]]),
        ("User8",  random.sample(ROLE_EMOTES, 3), [TEAM_EMOTES[1]]),
        ("User9",  random.sample(ROLE_EMOTES, 3), [TEAM_EMOTES[1]]),
        # No user for ("SUP", ["b"]) so you can react as Team B SUPP
    ]
    for user_name, roles, teams in user_data:
        class MockUser:
            def __init__(self, name):
                self.name = name
        user = MockUser(user_name)
        class MockEmoji:
            def __init__(self, name):
                self.name = name
            def __str__(self):
                return self.name
        class MockReaction:
            def __init__(self, emoji_name):
                self.emoji = MockEmoji(emoji_name)
        # React for each role
        for role in roles:
            reaction = MockReaction(role)
            await match.on_react(reaction, user)
        # React for each team
        for team in teams:
            reaction = MockReaction(team)
            await match.on_react(reaction, user)
        print(f"Simulated {user_name} with roles: {roles}, teams: {teams}")

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
        message = await channel.send("League of Legends Lobby\nReact with roles and teams to join!")
        match.message = message

        # Add reactions for roles and teams
        for emote_name in ROLE_EMOTES + TEAM_EMOTES:
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