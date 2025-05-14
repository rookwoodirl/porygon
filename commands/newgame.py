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
RIOT_REGION = 'americas'

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

class Summoner:
    def __init__(self, participant):
        self.puuid = participant.get('puuid')
        self.summoner_name = participant.get('summonerName')
        self.champion_id = participant.get('championId')
        self.champion = None  # Will be filled in async
        self.runes = []
        if 'perks' in participant and 'styles' in participant['perks']:
            for style in participant['perks']['styles']:
                if 'selections' in style:
                    self.runes.extend([sel['perk'] for sel in style['selections']])
        self.kda = (
            participant.get('kills', 0),
            participant.get('deaths', 0),
            participant.get('assists', 0)
        )
        self.winner = participant.get('win', False)

    async def fill_champion_name(self):
        self.champion = await get_champion_name(self.champion_id)

class MatchData:
    def __init__(self, match_id):
        self.match_id = match_id
        self._data = None
    
    async def initialize(self):
        await self.get_match_data()

    async def get_match_data(self):
        if self._data is not None:
            return self._data
        self._data = await get_match_details(self.match_id)
        return self._data

    async def summoners(self):
        """
        Returns a list of Summoner objects for each participant in the match,
        with champion names filled in.
        """
        data = await self.get_match_data()
        if not data or 'info' not in data or 'participants' not in data['info']:
            return []

        summoners = [Summoner(p) for p in data['info']['participants']]
        # Fill in champion names asynchronously
        await asyncio.gather(*(s.fill_champion_name() for s in summoners))
        return summoners

class Player:
    def __init__(self, discord_name, discord_id=None):
        self.discord_name = discord_name
        self.discord_id = discord_id
        self.preferred_roles = set()
        self.rank = DEFAULT_LP
        self.top_champs = []
        self._initialized = False
        self.puuid = None # the Riot id of the user

    async def get_current_match_id(self):
        """Get the current match ID for a player using their PUUID."""
        if not self.puuid:
            await self.initialize()
        if not self.puuid:
            return None
        
        url = f'https://{RIOT_REGION}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{self.puuid}'
        headers = {'X-Riot-Token': RIOT_API_KEY}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                game_data = await resp.json()
                return game_data.get('gameId')

    async def get_most_recent_match_id(self):
        if not self.puuid:
            # Ensure puuid is loaded
            await self.initialize()
        if not self.puuid:
            return None
        url = f'https://{RIOT_REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{self.puuid}/ids?start=0&count=1'
        headers = {'X-Riot-Token': RIOT_API_KEY}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"Failed to get match ids: {resp.status}")
                    return None
                match_ids = await resp.json()
                if not match_ids:
                    print("No matches found for puuid")
                    return None
                return match_ids[0]

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
                        self.puuid = summoner_data['puuid']
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
        self.player_preferences = {}  # user_id -> Player object
        self.message = None
        self.in_progress = False
        self.timeout = 0

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

    async def update(self):
        await self.message.edit(content=None, embed=self.description())

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
        else:
            embed.add_field(name="I'm waiting!", value='Click on the role emotes below to join this match', inline=False)
            embed.set_footer(text=f'{self.timeout} seconds until timeout...')

        # Lane Matchups
        if len(self.player_preferences) >= 10:
            lane_matchups = ""
            self.in_progress = True
            for role in ROLE_EMOTES:
                red_player = self.players[TEAM_EMOTES[0]][role]
                blue_player = self.players[TEAM_EMOTES[1]][role]
                red_name = getattr(red_player, 'discord_name', ' ')
                blue_name = getattr(blue_player, 'discord_name', ' ')
                red_mention = f"<@{getattr(red_player, 'discord_id', '')}>" if getattr(red_player, 'discord_id', None) else f"@{red_name}"
                blue_mention = f"<@{getattr(blue_player, 'discord_id', '')}>" if getattr(blue_player, 'discord_id', None) else f"@{blue_name}"
                emoji = self.emotes.get(role, role)
                left = f"{red_name:>{PAD}.{PAD}}"
                right = f"{blue_name:<{PAD}.{PAD}}"
                lane_matchups += f"`{left}` {emoji} `{right}`\t{red_mention} vs. {blue_mention}\n"
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

    def listen_for_game_start(self):
        async def listen():
            games = {}
            for _ in range(60): # 60 times
                await asyncio.sleep(10) # sleep 10 seconds
            for player in self.player_preferences.values():
                match_id = await player.get_current_game_id()
                if match_id is None:
                    continue
                if match_id not in games:
                    games[match_id] = 1
                else:
                    games[match_id] += 1
                
                if games[match_id] >= 5:
                    self.match_id = match_id
        asyncio.create_task(listen())

    async def on_react(self, reaction, user):
        if hasattr(reaction.emoji, 'name'):
            emoji_name = reaction.emoji.name
        else:
            emoji_name = str(reaction.emoji)
        user_id = user.id
        if emoji_name not in ROLE_EMOTES:
            return
        if user_id not in self.player_preferences:
            player = Player(str(user), user_id)
            await player.initialize()
            self.player_preferences[user_id] = player
            print(f"Created new player: {user_id}")
        player = self.player_preferences[user_id]
        if emoji_name in ROLE_EMOTES:
            player.preferred_roles.add(emoji_name)
            if user_id not in self.preferred_roles[emoji_name]:
                self.preferred_roles[emoji_name].append(user_id)
        await self.message.edit(content=None, embed=self.description())
        if self.has_enough_players():
            self.players = {team: {role: None for role in ROLE_EMOTES} for team in TEAM_EMOTES}
            self.roles_dfs()
            await self.message.edit(content=None, embed=self.description())

    async def on_unreact(self, reaction, user):
        if hasattr(reaction.emoji, 'name'):
            emoji_name = reaction.emoji.name
        else:
            emoji_name = str(reaction.emoji)
        user_id = user.id
        if emoji_name not in ROLE_EMOTES:
            return
        if user_id in self.player_preferences:
            player = self.player_preferences[user_id]
            if emoji_name in player.preferred_roles:
                player.preferred_roles.remove(emoji_name)
                if user_id in self.preferred_roles[emoji_name]:
                    self.preferred_roles[emoji_name].remove(user_id)
            if not player.preferred_roles:
                del self.player_preferences[user_id]
                for role in ROLE_EMOTES:
                    if user_id in self.preferred_roles[role]:
                        self.preferred_roles[role].remove(user_id)
        await self.update()
        if self.has_enough_players():
            self.players = {team: {role: None for role in ROLE_EMOTES} for team in TEAM_EMOTES}
            self.roles_dfs()
            await self.update()

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

async def delete_message_after_delay(match, delay=60, chunk=10):
    match.timeout = delay
    async def delete(match, delay, chunk):
        for _ in range(delay // chunk):
            await asyncio.sleep(chunk)
            match.timeout -= chunk
            await match.update()
        
        match.timeout = 0
        await match.message.delete()
        del match
    asyncio.create_task(delete(match, delay, chunk))

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
        channel = discord.utils.get(ctx.guild.channels, name=CHANNEL_NAME)
        if not channel and os.environ.get('ENV', 'prod') != 'dev':
            channel = await ctx.guild.create_text_channel(CHANNEL_NAME, category=ctx.channel.category)

        # Create a new match
        match = Match(emotes)
        
        # Send the initial message
        message = await channel.send(embed=match.description())
        match.message = message

        # Start a background task to delete the message after 60 seconds
        asyncio.create_task(delete_message_after_delay(match, delay=60))

        # Add reactions for roles
        for emote_name in ROLE_EMOTES:
            emoji = emotes.get(emote_name, emote_name)
            await message.add_reaction(emoji)

        # Simulate users
        if os.environ.get('ENV', 'prod') == 'dev':
            await simulate_users(match)

        # Set up reaction listener
        def check(reaction, user):
            return reaction.message.id == message.id and not user.bot

        def check_remove(reaction, user):
            return reaction.message.id == message.id and not user.bot

        while True:
            try:
                # Wait for either add or remove, whichever comes first
                add_task = asyncio.create_task(ctx.bot.wait_for('reaction_add', timeout=3600, check=check))
                remove_task = asyncio.create_task(ctx.bot.wait_for('reaction_remove', timeout=3600, check=check_remove))
                done, pending = await asyncio.wait(
                    [add_task, remove_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    reaction, user = task.result()
                    if task is add_task:
                        await match.on_react(reaction, user)
                    else:
                        await match.on_unreact(reaction, user)
            except asyncio.TimeoutError:
                await message.edit(content="Lobby timed out after 1 hour")
                await message.delete()
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

CHANNEL_NAME = 'lol-queue-pory'
if os.environ.get('ENV', 'prod') == 'dev':
    CHANNEL_NAME += '-dev'
async def run(ctx):
    if ctx.channel.name != CHANNEL_NAME:
        return
    
    async for message in ctx.channel.history(limit=None):
        if message.author == ctx.bot.user or message.content == '!newgame':
            try:
                await message.delete()
            except discord.NotFound:
                continue  # Message was already deleted
            except discord.Forbidden:
                print(f"Missing permissions to delete message {message.id}")
                continue
            except Exception as e:
                print(f"Error deleting message {message.id}: {e}")
                continue

    try:
        try:
            await ctx.message.delete()
        except discord.NotFound: # in case the message doesn't exist anymore
            pass
        return await new_game(ctx)
    except Exception as e:
        print("Error in run:", file=sys.stderr)
        print("Error type:", type(e).__name__, file=sys.stderr)
        print("Error message:", str(e), file=sys.stderr)
        print("Stack trace:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise

async def get_match_details(match_id):
    url = f'https://{RIOT_REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}'
    headers = {'X-Riot-Token': RIOT_API_KEY}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                print(f"Failed to get match details: {resp.status}")
                return None
            return await resp.json()