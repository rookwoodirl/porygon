import discord
from discord.ext import commands
import asyncio
import os
import random
import traceback
import sys
import json
import aiohttp
from dotenv import load_dotenv

load_dotenv()

ROLE_EMOTES = ['TOP', 'JGL', 'MID', 'BOT', 'SUP']
TEAM_EMOTES = ['🅰️', '🅱️']  # These are default Unicode emojis
SUMMONERS_FILE = 'data/summoners.json'
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
RIOT_API_BASE = 'https://na1.api.riotgames.com'
CHAMPION_DATA_URL = 'http://ddragon.leagueoflegends.com/cdn/13.24.1/data/en_US/champion.json'
DEFAULT_LP = 1300 # Gold 1

# Cache champion data
champion_data = None

async def get_champion_name(champion_id):
    global champion_data
    if champion_data is None:
        async with aiohttp.ClientSession() as session:
            async with session.get(CHAMPION_DATA_URL) as response:
                data = await response.json()
                champion_data = {int(v['key']): v['name'] for v in data['data'].values()}
    return champion_data.get(champion_id, f"Unknown Champion {champion_id}")

async def get_summoner_data(session, puuid):
    """Get summoner data using PUUID."""
    summoner_url = f'{RIOT_API_BASE}/lol/summoner/v4/summoners/by-puuid/{puuid}'
    headers = {'X-Riot-Token': RIOT_API_KEY}
    
    async with session.get(summoner_url, headers=headers) as response:
        if response.status != 200:
            return None, f"Error fetching summoner: {response.status}"
        summoner_data = await response.json()
    
    # Get ranked data
    ranked_url = f'{RIOT_API_BASE}/lol/league/v4/entries/by-summoner/{summoner_data["id"]}'
    async with session.get(ranked_url, headers=headers) as response:
        if response.status != 200:
            return None, f"Error fetching ranked data: {response.status}"
        ranked_data = await response.json()
    
    # Get champion mastery
    mastery_url = f'{RIOT_API_BASE}/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}'
    async with session.get(mastery_url, headers=headers) as response:
        if response.status != 200:
            return None, f"Error fetching mastery data: {response.status}"
        mastery_data = await response.json()
    
    return {
        'summoner': summoner_data,
        'ranked': ranked_data,
        'mastery': mastery_data
    }, None

def format_ranked_data(ranked_data):
    TIER_MAP = {
        'IRON' : 0,
        'BRONZE' : 400,
        'SILVER' : 800,
        'GOLD' : 1200,
        'PLATINUM' : 1400,
        'EMERALD' : 1800,
        'DIAMOND' : 2200,
        'MASTER' : 2600,
        'GRANDMASTER' : 3000,
        'CHALLENGER' : 3000
    }
    RANK_MAP = {
        'IV' : 0,
        'III' : 1,
        'II' : 2,
        'I' : 3
    }
    if not ranked_data:
        return "Unranked"
    
    # Find solo queue data
    solo_queue = next((q for q in ranked_data if q['queueType'] == 'RANKED_SOLO_5x5'), None)
    if not solo_queue:
        return DEFAULT_LP
    
    lp = TIER_MAP[solo_queue['tier']] + RANK_MAP[solo_queue['rank']]*100 + int(solo_queue['leaguePoints'])
    return lp

async def format_mastery_data(mastery_data):
    top_champs = sorted(mastery_data, key=lambda x: x['championPoints'], reverse=True)[:3]
    champ_names = []
    for champ in top_champs:
        name = await get_champion_name(champ['championId'])
        points = champ['championPoints']
        champ_names.append(f"{name} ({points:,} pts)")
    return champ_names

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

    # Get all emotes including custom ones
    emotes = {str(e.name): e for e in await guild.fetch_emojis()}
    # Add default emojis for teams
    emotes.update({'a': '🅰️', 'b': '🅱️'})
    return emotes

class Player:
    def __init__(self, discord_name):
        self.discord_name = discord_name
        self.preferred_roles = set()
        self.rank = DEFAULT_LP
        self.top_champs = []
        self._initialized = False

    async def initialize(self):
        """Async initialization to fetch summoner data."""
        if self._initialized:
            return

        try:
            with open(os.path.join('data', 'summoners.json'), 'r') as f:
                summoners = json.load(f)
                if self.discord_name in summoners:
                    summoner_data = summoners[self.discord_name]
                    if 'puuid' in summoner_data:
                        async with aiohttp.ClientSession() as session:
                            data, error = await get_summoner_data(session, summoner_data['puuid'])
                            if data:
                                self.rank = format_ranked_data(data['ranked']) or DEFAULT_LP
                                self.top_champs = await format_mastery_data(data['mastery'])
        except (FileNotFoundError, json.JSONDecodeError):
            pass  # Handle case where file doesn't exist or is invalid
        
        self._initialized = True

class Match:
    def __init__(self, emotes):
        self.emotes = emotes
        self.preferred_roles = {role: [] for role in ROLE_EMOTES}
        self.players = {team: {role: None for role in ROLE_EMOTES} for team in TEAM_EMOTES}
        self.player_preferences = {}  # discord_name -> Player object
        self.message = None

    def roles_dfs(self):
        def solutions(player_roles, roles_index=0, team_a={role : None for role in ROLE_EMOTES}, team_b={role : None for role in ROLE_EMOTES}):
            if roles_index >= len(ROLE_EMOTES) and None not in team_a.values() and None not in team_b.values():
                return [{ TEAM_EMOTES[0] : team_a.copy(), TEAM_EMOTES[1] : team_b.copy() }]
            role = ROLE_EMOTES[roles_index]

            all_solutions = []

            for player in player_roles:
                if player in team_a.values() or player in team_b.values():
                    continue
                if role in player.preferred_roles:
                    if team_a[role] is None:
                        team_a_copy = team_a.copy()
                        team_b_copy = team_b.copy()
                        team_a_copy[role] = player
                        all_solutions.extend(solutions(player_roles, roles_index, team_a_copy, team_b_copy))
                    if team_b[role] is None and team_a[role] is not None:
                        team_a_copy = team_a.copy()
                        team_b_copy = team_b.copy()
                        team_b_copy[role] = player
                        all_solutions.extend(solutions(player_roles, roles_index+1, team_a_copy, team_b_copy))

            return all_solutions
        sols = solutions(list(self.player_preferences.values()))
        def lp_diff(solution):
            team_a, team_b = list(solution.values())
            team_a, team_b = [player.rank for player in team_a.values()], [player.rank for player in team_b.values()]
            return abs(sum(team_a) - sum(team_b))
        self.players = min(sols, key=lambda x: lp_diff(x))

    def description(self):
        PAD = max([len(player.discord_name) for player in self.player_preferences.values()]) if self.player_preferences else 4
        embed = discord.Embed(
            title="League of Legends Lobby",
            description="React with roles to join!",
            color=discord.Color.blue()
        )
        # Queued Players
        if self.player_preferences:
            players_desc = ""
            for player in self.player_preferences.values():
                roles = ''.join([
                    f'{self.emotes.get(role, ":" + role + ":")}' for role in sorted(player.preferred_roles)
                ]) if player.preferred_roles else 'None'
                players_desc += f'`{player.discord_name:<{PAD}.{PAD}}` `{str(player.rank):<{4}.{4}}LP` : {roles}\n'
            embed.add_field(name="Queued Players", value=players_desc, inline=False)

        # Lane Matchups
        lane_matchups = ""
        for role in ROLE_EMOTES:
            red_player = getattr(self.players[TEAM_EMOTES[0]][role], 'discord_name', "Empty")
            blue_player = getattr(self.players[TEAM_EMOTES[1]][role], 'discord_name', "Empty")
            emoji = self.emotes.get(role, role)
            left = f"{red_player:<{PAD}.{PAD}}"
            right = f"{blue_player:<{PAD}.{PAD}}"
            lane_matchups += f"`{left}` {emoji} `{right}`\t@{red_player} vs. @{blue_player}\n"
        embed.add_field(name="Lane Matchups", value=lane_matchups, inline=False)

        # LP Difference
        team_a_lp = sum(getattr(self.players[TEAM_EMOTES[0]][role], 'rank', 0) for role in ROLE_EMOTES)
        team_b_lp = sum(getattr(self.players[TEAM_EMOTES[1]][role], 'rank', 0) for role in ROLE_EMOTES)
        embed.set_footer(text=f"Team Balance: LP Difference = {abs(team_a_lp - team_b_lp)}")
        return embed

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
            player = Player(discord_tag)
            await player.initialize()  # Initialize the player asynchronously
            self.player_preferences[discord_tag] = player
            print(f"Created new player: {discord_tag}")  # Debug print

        player = self.player_preferences[discord_tag]
        
        if emoji_name in ROLE_EMOTES:
            player.preferred_roles.add(emoji_name)
            if emoji_name not in self.preferred_roles[emoji_name]:
                self.preferred_roles[emoji_name].append(discord_tag)

        # Update the message with current state
        await self.message.edit(content=None, embed=self.description())

        # Always clear assignments and re-run DFS if enough players and roles
        if self.has_enough_players():
            self.players = {team: {role: None for role in ROLE_EMOTES} for team in TEAM_EMOTES}
            self.roles_dfs()
            await self.message.edit(content=None, embed=self.description())

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
    await match.message.edit(content=None, embed=match.description())
    
    # Run DFS if we have enough players
    if match.has_enough_players():
        match.roles_dfs()
        await match.message.edit(content=None, embed=match.description())

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
        channel = discord.utils.get(ctx.guild.channels, name='lol-queue-pory')
        if not channel:
            channel = await ctx.guild.create_text_channel('lol-queue-pory', category=ctx.channel.category)

        # Create a new match
        match = Match(emotes)
        
        # Send the initial message
        message = await channel.send(embed=match.description())
        match.message = message

        # Add reactions for roles
        for emote_name in ROLE_EMOTES:
            emoji = emotes.get(emote_name, emote_name)
            await message.add_reaction(emoji)

        # Simulate users
        # await simulate_users(match)

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