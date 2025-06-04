import os
import aiohttp
from typing import List, Dict, Optional
from dotenv import load_dotenv
import asyncio
import discord
import json
import itertools
import traceback
from utils.postgres import RiotPostgresManager
from discord.ext import commands
import random

load_dotenv()
bot = None # this is set by main.py

db_conn = RiotPostgresManager()

RIOT_API_KEY = os.getenv('RIOT_API_KEY')
RIOT_API_BASE = 'https://na1.api.riotgames.com'
RIOT_REGION = 'americas'
RIOT_REGIONAL_ROUTING = 'na1'  # Regional routing value for North America
RIOT_PLATFORM_ROUTING = 'na1'  # Platform routing value for North America
DDRAGON_VERSION = '15.10.1'

RIOT_SPEC_MATCH_URL = f'{RIOT_API_BASE}/lol/spectator/v5/active-games/by-summoner/' + '{puuid}'
RIOT_DONE_MATCH_URL = f'https://{RIOT_REGION}.api.riotgames.com/lol/match/v5/matches/' + '{matchId}'

TEAM_A_ID = 100
TEAM_B_ID = 200

class Participant:
    """
    Represents a participant object from a Summoner's Rift game
    """
    def __init__(self, participant: Dict):
        self.data = participant  # the participant data from riot api
        self.champion_name = participant.get('championName')
        self.champion_id = participant.get('championId')
        self.puuid = participant.get('puuid')
        self.summoner_name = (
            participant.get('riotIdGameName') or
            participant.get('summonerName') or
            participant.get('puuid')  # fallback to puuid if no name
        )
        if 'riotIdTagline' in participant:
            self.summoner_name = self.summoner_name + '#' + participant.get('riotIdTagline')
        self.team_id = participant.get('teamId')
        self.win = participant.get('win', False)
        self.kills = participant.get('kills')
        self.deaths = participant.get('deaths')
        self.assists = participant.get('assists')
        self.champion_emoji = EmojiHandler.champion_emoji_by_id(self.champion_id)
    
    def formatted(self, reverse=False):
        pad = 16 # max([len(SummonerProfile.SUMMONER_LOOKUP.get(p.summoner_name, p.summoner_name.split('#')[0])) for p in participants])
        k, d, a = (self.kills, self.deaths, self.assists)

        if k is None or d is None or a is None:
            kda = f'`{' '*8}`'
        else:
            kda = f'`{str(k).rjust(2, ' ')}/{str(d).rjust(2, ' ')}/{str(a).rjust(2, ' ')}`'
        
        if self.summoner_name in SummonerProfile.SUMMONER_LOOKUP:
            summoner_name = SummonerProfile.SUMMONER_LOOKUP.get(self.summoner_name).discord_name
        else:
            summoner_name = self.summoner_name.split('#')[0]

        if reverse:
            summoner_name = f'`{summoner_name.rjust(pad, ' ')}`'
        else:
            summoner_name = f'`{summoner_name.ljust(pad, ' ')}`'

        if not self.champion_emoji:
            champion_emoji = EmojiHandler.DEFAULT_EMOJI
        else:
            champion_emoji = self.champion_emoji
        

        if reverse:
            return ''.join([summoner_name, champion_emoji, kda])
        else:
            return ''.join([kda, champion_emoji, summoner_name])

class EmojiHandler:
    _champion_data = None
    _emojis = None
    _initialized = False

    @classmethod
    async def initialize(cls):
        await EmojiHandler._init_champion_data()
        EmojiHandler._emojis = { emoji.name.upper() : emoji for emoji in await bot.fetch_application_emojis() }
        EmojiHandler._initialized = True

    @classmethod
    async def _init_champion_data(cls):
        """Initialize champion data from Data Dragon"""
        if cls._champion_data is not None:
            return

        url = f'http://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/data/en_US/champion.json'
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get champion data: {response.status}")
                data = await response.json()
                cls._champion_data = {str(v['key']): v['name'] for v in data['data'].values()}

    @classmethod
    def champion_id_to_name(cls, champion_id: str) -> str:
        """Convert a champion ID to the champion name"""
        return cls._champion_data.get(str(champion_id), f"Unknown Champion {champion_id}")

    @classmethod
    def champion_emoji_by_id(cls, champion_id: str):
        """Get champion emoji by ID"""
        champion_name = cls.champion_id_to_name(champion_id)
        return cls.champion_emoji_by_name(champion_name)

    DEFAULT_EMOJI = ':black_square_button:' # TODO change this into an emoji instead of a string
    @classmethod
    def champion_emoji_by_name(cls, champion_name: str):
        """Get champion emoji by name"""
        formatted_champion_name = ''.join(char for char in champion_name if char in 'abcdefghijklmnopqrstuvwxyz' + 'abcdefghijklmnopqrstuvwxyz'.upper()).upper()

        if formatted_champion_name in EmojiHandler._emojis:
            return str(EmojiHandler._emojis[formatted_champion_name])
        else:
            return EmojiHandler.DEFAULT_EMOJI
            """
            async def fetch_new_emoji():
                url = f'http://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/img/champion/{champion_name}.png'
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            print(f"Failed to get champion icon for {champion_name}")
                            return None
                        image_data = await response.read()
                        
                        # Create new emoji
                        try:
                            emoji = await bot.create_application_emoji(
                                name=champion_name,
                                image=image_data
                            )
                            print(f'Created {emoji.name} for Pory!')
                            return emoji
                        except Exception as e:
                            print(f"Failed to create emoji for {champion_name}: {e}")
                            return None
            """
            # asyncio.run(fetch_new_emoji()) # TODO creat_task this in an asynchronous thread-safe way 
            

    @classmethod
    async def summoner_profile_picture(cls, picture_id: str):
        """Get or create profile picture emoji"""
        emojis = {str(emoji.name): emoji for emoji in await bot.fetch_application_emojis()}
        if f'pp_{picture_id}' not in emojis:
            # Get profile picture from Data Dragon
            url = f'http://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/img/profileicon/{picture_id}.png'
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        print(f"Failed to get profile picture {picture_id}")
                        return None
                    image_data = await response.read()
                    
                    # Create new emoji
                    try:
                        emoji = await bot.create_application_emoji(
                            name=f'pp_{picture_id}',
                            image=image_data
                        )
                        return emoji
                    except Exception as e:
                        print(f"Failed to create profile picture emoji: {e}")
                        return None
        else:
            return emojis[f'pp_{picture_id}']

    ROLE_EMOJI_NAMES_SORTED = ['TOP', 'JGL', 'MID', 'BOT', 'SUP']
    @classmethod
    async def role_emojis(cls):
        return { str(emoji.name) : emoji for emoji in await bot.fetch_application_emojis() if str(emoji.name) in EmojiHandler.ROLE_EMOJI_NAMES_SORTED }

class SummonerProfile:
    """
    Represents the out-of-game profile of a League of Legends player
    Includes functions that do API calls for:
        profile summary
        match history
        mastery points
    Can optionally be associated with a Discord user's profile
    """
    SUMMONER_LOOKUP = {}

    def __init__(self, discord_name: str, player_tag: Optional[str] = None, spoof=False):
        self.player_tag = player_tag  # Player#NA1
        self.discord_name = discord_name
        self._initialized = False
        self.spoof = spoof
        
        # Data that will be loaded by initialize()
        self._puuid = None
        self._summoner_id = None
        self._account_id = None
        self._rank = 1300
        self._summoner_data = None
        self._ranked_data = None
        self._mastery_data = None

        SummonerProfile.SUMMONER_LOOKUP[self.discord_name] = self

    async def fetch_json(self, url, headers):
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch: {url} ({response.status})")
                return await response.json()

    async def initialize(self):
        """Load all summoner data upfront"""
        if self._initialized:
            return

        # Load from summoners.json if no player_tag provided
        if self.player_tag is None:
            try:
                with open(os.path.join('data', 'summoners.json')) as f:
                    summoners = json.load(f)
                    if self.spoof:
                        lookup = 'UserX'
                    else:
                        lookup = self.discord_name
                    if lookup in summoners:
                        summoner_data = summoners[lookup]
                        self.player_tag = summoner_data.get('summoner_name') + '#' + summoner_data.get('tag')
                        self._puuid = summoner_data.get('puuid')
            except (FileNotFoundError, json.JSONDecodeError):
                pass

        if self.spoof:
            self._initialized = True
            return
            # raise Exception(f"No player tag found for {self.discord_name}")

        # Get PUUID
        if self.player_tag is None:
            return
        game_name, tag_line = self.player_tag.split('#')
        url = f'https://{RIOT_REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}'
        headers = {'X-Riot-Token': RIOT_API_KEY}
        data = await self.fetch_json(url, headers)
        self._puuid = data['puuid']

        # Get summoner data
        url = f'{RIOT_API_BASE}/lol/summoner/v4/summoners/by-puuid/{self._puuid}'
        data = await self.fetch_json(url, headers)
        self._summoner_data = data
        self._summoner_id = data['id']

        # Get ranked data
        url = f'{RIOT_API_BASE}/lol/league/v4/entries/by-summoner/{self._summoner_id}'
        data = await self.fetch_json(url, headers)
        self._ranked_data = data

        # Get mastery data
        url = f'{RIOT_API_BASE}/lol/champion-mastery/v4/champion-masteries/by-puuid/{self._puuid}'
        data = await self.fetch_json(url, headers)
        self._mastery_data = data

        # Calculate rank
        self._calculate_rank()
        
        self._initialized = True

        if self.player_tag:
            summoner_name, summoner_tag = self.player_tag.split('#')
            db_conn.store_summoner(self.discord_name, summoner_name, summoner_tag, self._puuid)

        print(f'Successfully initialize: {self.discord_name} ({self.player_tag})')

    def _calculate_rank(self):
        """Calculate total LP from ranked data"""
        DEFAULT_LP = 1300  # Gold 1

        try:
            # Find solo queue data
            solo_queue = next((q for q in self._ranked_data if q['queueType'] == 'RANKED_SOLO_5x5'), None)
            if not solo_queue:
                self._rank = DEFAULT_LP
                return

            # Calculate total LP
            TIER_MAP = {
                'IRON': 0,
                'BRONZE': 400,
                'SILVER': 800,
                'GOLD': 1200,
                'PLATINUM': 1600,
                'EMERALD': 2000,
                'DIAMOND': 2400,
                'MASTER': 2800,
                'GRANDMASTER': 3200,
                'CHALLENGER': 3200
            }
            RANK_MAP = {
                'IV': 0,
                'III': 100,
                'II': 200,
                'I': 300
            }

            tier_lp = TIER_MAP.get(solo_queue['tier'], 0)
            rank_lp = RANK_MAP.get(solo_queue['rank'], 0)
            league_points = solo_queue['leaguePoints']

            self._rank = tier_lp + rank_lp + league_points
        except Exception as e:
            print(f"Error calculating rank for {self.discord_name}: {e}")
            self._rank = DEFAULT_LP

    def get_rank(self) -> int:
        """Get the calculated rank value for this summoner.
        Returns the total LP value calculated from their ranked data.
        If no ranked data is available, returns the default value (1300 LP)."""
        if not self._initialized:
            raise Exception("SummonerProfile must be initialized before getting rank")
        if self._rank is None:
            self._calculate_rank()  # Try to calculate rank if it's None
        return self._rank if self._rank is not None else 1300  # Default to 1300 if still None

    async def match_history(self, limit: int = 5) -> List[str]:
        """Get recent match IDs"""
        if not self._puuid:
            await self.initialize()

        url = f'https://{RIOT_REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{self._puuid}/ids'
        params = {'start': 0, 'count': limit}
        headers = {'X-Riot-Token': RIOT_API_KEY}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get match history: {response.status}")
                return await response.json()

    async def get_current_match(self) -> Optional[Dict]:
        """Get current game data if the player is in a game, or most recent match if ENV=dev."""
        try:
        
            # Return current live match data using v5 spectator endpoint
            if not self._puuid:
                return None
            url = RIOT_SPEC_MATCH_URL.format(puuid=self._puuid)
            headers = {'X-Riot-Token': RIOT_API_KEY}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 404:
                        print(f"Player {self.discord_name} is not currently in a game")
                        return None  # Player is not in a game
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"Failed to get current match: {response.status}")
                        print(f"Error response: {error_text}")
                        raise Exception(f"Failed to get current match: {response.status} - {error_text}")
                    
                    return await response.json()
        except Exception as e:
            print(e)
            return None


class SimulatedReaction:
    def __init__(self, emoji):
        self.emoji = emoji

class MatchMessage:
    MESSAGES = {}
    def __init__(self, guild_id):
        """
        Users react to a post with their role and 
        """
        self.teams = []
        self.players = {}
        self.player_preferences = {}
        self.guild_id = guild_id
        self.message = None
        self.timeout = 60*15 # 15 minutes
        self.queued_players = []
        self.spectator_data = {}
        self.match_data = {}

    async def simulate_users(self):
        """Simulate 9 users with hardcoded preferences."""
        # Each tuple: (username, [roles])
        role_emotes = await EmojiHandler.role_emojis()
        user_data = [
            ("User0",  random.sample(list(role_emotes.values()), 3)),
            ("User1",  random.sample(list(role_emotes.values()), 3)),
            ("User2",  random.sample(list(role_emotes.values()), 3)),
            ("User3",  random.sample(list(role_emotes.values()), 3)),
            ("User4",  random.sample(list(role_emotes.values()), 3)),
            ("User5",  random.sample(list(role_emotes.values()), 3)),
            ("User6",  random.sample(list(role_emotes.values()), 3)),
            ("User7",  random.sample(list(role_emotes.values()), 3)),
            ("User8",  random.sample(list(role_emotes.values()), 3)),
        ]
        
        # Directly update the data structures
        for user_name, roles in user_data:
            for role in roles:
                if len(self.players) < 10:
                    profile = SummonerProfile(user_name, spoof=True)
                    await profile.initialize()
                    self.players[user_name] = profile
                    self.player_preferences[user_name] = [role.name for role in roles]
                else:
                    await self.on_react(SimulatedReaction(role), user_name)

    async def initialize(self):
        try:
            # If guild_id is a Message object, get the guild_id from it
            if hasattr(self.guild_id, 'guild'):
                guild_id = self.guild_id.guild.id
            else:
                guild_id = int(self.guild_id)

            guild = bot.get_guild(guild_id)
            if not guild:
                guild = await bot.fetch_guild(guild_id)
            
            # Use the existing channel
            channel_name = 'lol-match-history'
            if os.environ.get('ENV', 'prod') == 'dev':
                channel_name += '-dev'

            history_channel = discord.utils.get(guild.text_channels, name=channel_name)
            if history_channel is None:
                return

            self.message = await history_channel.send(embed=self.description())
            MatchMessage.MESSAGES[self.message.id] = self

            if os.environ.get('ENV', 'prod') == 'dev':
                await self.simulate_users()

            self.role_emojis = await EmojiHandler.role_emojis()

            # Add reactions for roles
            for emoji in EmojiHandler.ROLE_EMOJI_NAMES_SORTED:
                await self.message.add_reaction(self.role_emojis[emoji])

            async def listen_for_reactions():
                try:
                    # Use raw reaction events instead of wait_for
                    async def on_raw_reaction_add(payload):
                        if payload.message_id != self.message.id:
                            return
                        if payload.user_id == bot.user.id:
                            return
                        if not hasattr(payload.emoji, 'name') or payload.emoji.name not in self.role_emojis:
                            return
                        
                        # Get the reaction and user objects
                        channel = bot.get_channel(payload.channel_id)
                        message = await channel.fetch_message(payload.message_id)
                        user = await bot.fetch_user(payload.user_id)
                        reaction = next((r for r in message.reactions if r.emoji.name == payload.emoji.name), None)
                        
                        if reaction:
                            await self.on_react(reaction, user)

                    async def on_raw_reaction_remove(payload):
                        if payload.message_id != self.message.id:
                            return
                        if payload.user_id == bot.user.id:
                            return
                        if not hasattr(payload.emoji, 'name') or payload.emoji.name not in self.role_emojis:
                            return
                        
                        # Get the reaction and user objects
                        channel = bot.get_channel(payload.channel_id)
                        message = await channel.fetch_message(payload.message_id)
                        user = await bot.fetch_user(payload.user_id)
                        reaction = next((r for r in message.reactions if r.emoji.name == payload.emoji.name), None)
                        
                        if reaction:
                            await self.on_unreact(reaction, user)

                    # Add event listeners
                    bot.add_listener(on_raw_reaction_add, 'on_raw_reaction_add')
                    bot.add_listener(on_raw_reaction_remove, 'on_raw_reaction_remove')
                    
                    # Keep the task running
                    while True:
                        await asyncio.sleep(1)
                        if self.message is None:
                            # Remove event listeners when message is deleted
                            bot.remove_listener(on_raw_reaction_add, 'on_raw_reaction_add')
                            bot.remove_listener(on_raw_reaction_remove, 'on_raw_reaction_remove')
                            return
                            
                except Exception as e:
                    print(f"Error in reaction listener: {e}")
                    traceback.print_exc()

            async def update_message():
                UPDATE_RATE = 15 # update every 5 seconds
                while True:
                    await asyncio.sleep(UPDATE_RATE) # update every 5 seconds
                    self.timeout -= UPDATE_RATE
                    if self.message is None:
                        self.timeout = 0
                        return
                    
                    try:
                        await self.message.edit(content=None, embed=self.description())
                    except Exception:
                        traceback.print_exc()

            async def listen_for_match():
                while True:
                    if os.environ.get('ENV', 'prod') == 'dev':
                        print('Dev detected. Skipping live match listen...')
                        break
                    print('Listening for live match...')
                    await asyncio.sleep(30)
                    if not self.players:
                        continue
                    puuids = [player._puuid for player in self.players.values()]

                    spectator_data = await next(iter(self.players.values())).get_current_match()

                    if not spectator_data:
                        continue

                    live_puuids = [participant['puuid'] for participant in spectator_data.get('participants')]
                    
                    if len([puuid for puuid in puuids if puuid in live_puuids]) >= 6:
                        self.spectator_data = spectator_data
                        break

                if os.environ.get('ENV', 'prod') == 'dev':
                    match_id = os.environ.get('MATCH_ID', 'NA1_5298648678')
                else:
                    match_id = self.spectator_data['gameId']
                while True:
                    print('Listening for match to finish...')
                    url = RIOT_DONE_MATCH_URL.format(matchId=match_id)
                    headers = {'X-Riot-Token': RIOT_API_KEY}
                    print(url)
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers=headers) as response:
                            if response.status != 200:
                                print(response)
                                await asyncio.sleep(60)
                                continue
                            
                            self.match_data = await response.json()
                            if not self.match_data:
                                await asyncio.sleep(60)
                                continue
                            break
                    await asyncio.sleep(30)

            asyncio.create_task(update_message())
            asyncio.create_task(listen_for_reactions())
            asyncio.create_task(listen_for_match())

        except Exception as e:
            traceback.print_exc()

    async def on_react(self, reaction, user):
        if reaction.emoji.name not in self.role_emojis:
            return
        
        real_reaction_emoji = [r.emoji for r in self.message.reactions if r.emoji.name == reaction.emoji.name]
        if real_reaction_emoji:
            await self.message.add_reaction(real_reaction_emoji[0])

        discord_user = str(user)
        if discord_user not in self.player_preferences:
            self.player_preferences[discord_user] = []
        if reaction.emoji.name not in self.player_preferences[discord_user]:
            self.player_preferences[discord_user] += [reaction.emoji.name]

        if discord_user not in self.players:
            if len(self.players) < 10:
                profile = SummonerProfile(discord_user)
                await profile.initialize()
                self.players[discord_user] = profile
            elif discord_user not in self.queued_players:
                self.queued_players.append(discord_user)

        if len(self.player_preferences) >= 10:
            print('Choosing roles!')
            self._choose_roles()
            self.timeout = 60*45 # 45 minutes

        else:
            self.teams = {}
        

        await self.message.edit(content=None, embed=self.description())

    async def on_unreact(self, reaction, user):
        discord_user = str(user)
        if discord_user not in self.player_preferences:
            return
        
        # Fetch the message to get current reactions
        try:
            self.message = await self.message.channel.fetch_message(self.message.id)
            real_reaction_emoji = [r.emoji for r in self.message.reactions if r.emoji.name == reaction.emoji.name]
            if real_reaction_emoji:
                await self.message.remove_reaction(real_reaction_emoji[0])
        except Exception as e:
            print(f"Error handling reaction removal: {e}")
            traceback.print_exc()
        
        prefs = self.player_preferences[discord_user]

        if prefs == [reaction.emoji.name]:
            del self.player_preferences[discord_user]
            if discord_user in self.players:
                del self.players[discord_user]
                if self.queued_players:
                    discord_user = self.queued_players.pop(0)
                    profile = SummonerProfile(discord_user)
                    await profile.initialize()
                    self.players[discord_user] = profile
            if discord_user in self.queued_players:
                self.queued_players = [player for player in self.queued_players if player != discord_user]
        else:
            self.player_preferences[discord_user] = [role for role in prefs if role != str(reaction.emoji.name)]

        if len(self.player_preferences) >= 10:
            print('Choosing roles after unreact!')
            self._choose_roles()
        else:
            self.teams = {}

        await self.message.edit(content=None, embed=self.description())

    def _choose_roles(self, roles=EmojiHandler.ROLE_EMOJI_NAMES_SORTED):
        """
        players: List[Player] (must be length 10)
        roles: List[str] (default: ['TOP', 'JGL', 'MID', 'BOT', 'SUP'])
        Returns: (team_a, team_b, lp_diff)
            where team_a/team_b: dict of role -> Player
        """
        players = self.players
        print("Choosing roles for players:", list(players.keys()))
        assert len(players) == 10, "Must have exactly 10 players"

        best_diff = float('inf')
        best_assignment = None

        # All possible ways to split 10 players into two teams of 5
        for team_a_players in itertools.combinations(players, 5):
            team_b_players = [p for p in players if p not in team_a_players]

            # Try to assign roles for team A
            for perm_a in itertools.permutations(team_a_players):
                team_a_roles = {}
                used = set()
                for role, player in zip(roles, perm_a):
                    if role in self.player_preferences[player] and player not in used:
                        team_a_roles[role] = player
                        used.add(player)
                if len(team_a_roles) != 5:
                    continue  # Not all roles filled with preferences

                # Try to assign roles for team B
                for perm_b in itertools.permutations(team_b_players):
                    team_b_roles = {}
                    used_b = set()
                    for role, player in zip(roles, perm_b):
                        if role in self.player_preferences[player] and player not in used_b:
                            team_b_roles[role] = player
                            used_b.add(player)
                    if len(team_b_roles) != 5:
                        continue

                    # Both teams have valid assignments
                    try:
                        lp_a = sum(self.players[p].get_rank() for p in team_a_roles.values())
                        lp_b = sum(self.players[p].get_rank() for p in team_b_roles.values())
                        diff = abs(lp_a - lp_b)
                        if diff < best_diff:
                            best_diff = diff
                            best_assignment = (team_a_roles.copy(), team_b_roles.copy(), diff)
                        # Early exit if perfect balance
                        if diff == 0:
                            print("Found perfect balance!")
                            self.teams = best_assignment
                            return best_assignment
                    except Exception as e:
                        print(f"Error calculating team balance: {e}")
                        continue

        self.teams = []
        team_a, team_b, lp_diff = best_assignment

        for role in EmojiHandler.ROLE_EMOJI_NAMES_SORTED:
            self.teams.append(Participant({
                'riotIdGameName' : team_a[role],
                'teamId' : TEAM_A_ID
            }))
        for role in EmojiHandler.ROLE_EMOJI_NAMES_SORTED:
            self.teams.append(Participant({
                'riotIdGameName' : team_b[role],
                'teamId' : TEAM_B_ID
            }))

        print('Chose roles!')

    def description(self) -> discord.Embed:
        embed = discord.Embed(
            title="League of Legends Lobby",
            description='',
            color=discord.Color.blue()
        )

        embed.set_footer(text=f"Timeout: {self.timeout // 60}m {self.timeout % 60}s")

        # add embed that shows player preferences
        lines = [f'`{discord_user:<{14}.{14}}` : {''.join(str(self.role_emojis[role]) for role in roles)}' for discord_user, roles in self.player_preferences.items()]

        embed.add_field(name='Players', value='\n'.join(lines[::2]), inline=True)
        embed.add_field(name='...', value='\n'.join(lines[1::2]), inline=True)
        embed.add_field(name='In Queue', value='\n'.join(self.queued_players), inline=True)


        def format(participants):
            print(type(participants))

            team_a = [Participant(p) for p in participants if p['teamId'] == TEAM_A_ID]
            team_b = [Participant(p) for p in participants if p['teamId'] == TEAM_B_ID]

            lines = []

            for player_a, role, player_b in zip(team_a, EmojiHandler.ROLE_EMOJI_NAMES_SORTED, team_b):
                lines.append(''.join([player_a.formatted(), str(EmojiHandler._emojis[role]), player_b.formatted(reverse=True)]))
            
            return '\n'.join(lines)
        

        if self.match_data:
            print('done')
            data_string = format(self.match_data['info']['participants'])
        elif self.spectator_data:
            print('spec')
            data_string = format(self.spectator_data['participants'])
        elif self.teams:
            print('team')
            data_string = format(self.teams)
        else:
            data_string = ''

        if data_string:
            embed.add_field(name='Teams', value=data_string)

        return embed
        

if __name__ == '__main__':
    import asyncio
    import os
    from dotenv import load_dotenv
    import discord
    from discord.ext import commands

    load_dotenv()

    # Create bot instance with all necessary intents
    intents = discord.Intents.all()  # Enable all intents
    bot = commands.Bot(command_prefix="!", intents=intents)
    # Set the global bot variable
    globals()['bot'] = bot

    @bot.event
    async def on_ready():

        # Initialize emoji handler
        await EmojiHandler.initialize()

        # Create match message
        message = MatchMessage(os.environ.get('SHINSEKAI_ID'))
        await message.initialize()

    # Run the bot
    bot.run(os.environ.get('DISCORD_API_KEY'))
