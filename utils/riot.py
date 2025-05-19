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

load_dotenv()
bot = None # this is set by main.py

db_conn = RiotPostgresManager()

RIOT_API_KEY = os.getenv('RIOT_API_KEY')
RIOT_API_BASE = 'https://na1.api.riotgames.com'
RIOT_REGION = 'americas'
DDRAGON_VERSION = '15.10.1'

class Summoner:
    """
    Represents a participant object from a Summoner's Rift game
    """
    def __init__(self, participant: Dict, match):
        self.data = participant  # the participant data from riot api
        self.champion_name = participant.get('championName')
        self.champion_id = participant.get('championId')
        self.puuid = participant.get('puuid')
        self.summoner_name = (
            participant.get('riotIdGameName') or
            participant.get('summonerName') or
            participant.get('puuid')  # fallback to puuid if no name
        ) + '#' + participant.get('riotIdTagline')
        self.team_id = participant.get('teamId')
        self.win = participant.get('win', False)
        self.kills = participant.get('kills', 0)
        self.deaths = participant.get('deaths', 0)
        self.assists = participant.get('assists', 0)
        self.champion_level = participant.get('champLevel', 0)
        self.total_damage_dealt = participant.get('totalDamageDealtToChampions', 0)
        self.vision_score = participant.get('visionScore', 0)
        self.gold_earned = participant.get('goldEarned', 0)
        self.champion_emoji = EmojiHandler.champion_emoji_by_id(self.champion_id)

    def kda(self):
        return (self.kills, self.deaths, self.assists)

    def kda_ratio(self) -> float:
        if self.deaths == 0:
            return self.kills + self.assists
        return (self.kills + self.assists) / self.deaths

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
            print(champion_name)
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
        """Get the player's current LP"""
        return self._rank

    def get_mastery(self) -> List[Dict]:
        """Get champion mastery data"""
        if not self._initialized:
            raise Exception("SummonerProfile not initialized")
        return self._mastery_data

    def get_profile_summary(self) -> Dict:
        """Get comprehensive profile summary"""
        if not self._initialized:
            raise Exception("SummonerProfile not initialized")
            
        return {
            'summoner': self._summoner_data,
            'ranked': self._ranked_data,
            'top_champions': sorted(self._mastery_data, key=lambda x: x['championPoints'], reverse=True)[:3],
            'profile_picture': f':{self._summoner_data.get("profileIconId")}:'
        }

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
        if os.environ.get('ENV', 'prod') == 'dev':
            if not self._puuid:
                if not self._initialized:
                    await self.initialize()
                if not self._puuid:
                    print("No PUUID after initialize!")
                    return None
            url = f'https://{RIOT_REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{self._puuid}/ids?start=0&count=1'
            headers = {'X-Riot-Token': RIOT_API_KEY}
            print("Fetching match IDs from:", url)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    print("Response status:", resp.status)
                    match_ids = await resp.json()
                    print("Match IDs:", match_ids)
                    if not match_ids:
                        print("No recent matches found!")
                        return None
                    match_id = match_ids[0]
            # Get match data
            url = f'https://{RIOT_REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}'
            print("Fetching match data from:", url)
            await asyncio.sleep(5)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    print("Match data response status:", resp.status)
                    if resp.status != 200:
                        print("Failed to fetch match data!")
                        return None
                                        
                    return await resp.json()
        
        else:
            # Return current live match data
            if not self._summoner_id:
                await self._get_summoner_data()
            url = f'{RIOT_API_BASE}/lol/spectator/v4/active-games/by-summoner/{self._summoner_id}'
            headers = {'X-Riot-Token': RIOT_API_KEY}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 404:
                        return None  # Player is not in a game
                    if response.status != 200:
                        raise Exception(f"Failed to get current match: {response.status}")
                        return None
                    
                    return await response.json()

    async def get_current_match_id(self):
        """Return the current match ID if the player is in a game, or None otherwise."""
        match = await self.get_current_match()
        if match:
            return match['metadata']['matchId']

class MatchMessage:
    MESSAGES = {}
    def __init__(self, command_message):
        """
        Users react to a post with their role and 
        """
        self.teams = {}
        self.players = {}
        self.player_preferences = {}
        self.role_emojis = []
        self.command_message = command_message
        self.message = None
        self.timeout = 300
        self.match_data = None
        self.queued_players = []



        async def update():
            while True:
                await asyncio.sleep(5)
                self.timeout -= 5
                try:
                    if self.message is not None:
                        if self.match_data is not None and self.match_data.completed:
                            # don't delete
                            return
                        if self.timeout <= 0:
                            try:
                                await self.message.delete()
                                return
                            except Exception:
                                return
                        else:
                            await self.update_message()
                            self.dump_to_file()
                except Exception:
                    traceback.print_exc()


        asyncio.create_task(update())

    async def update_message(self):
        if self.message is not None:
            await self.message.edit(content=None, embed=self.description())


    def dump_to_file(self):
        if self.match_data and self.match_id:
            with open(os.path.join('data', 'matches', f'{self.match_id}.json', 'w+')) as f:
                json.dump(self.match_data, f, indent=2)
            

    async def initialize(self):
        guild = self.command_message.guild

                
        channel_name = 'lol-match-history'
        if os.environ.get('ENV', 'prod') == 'dev':
            channel_name += '-dev'

        history_channel = discord.utils.get(guild.text_channels, name=channel_name)
        if history_channel is None:
            history_channel = await guild.create_text_channel(channel_name)

        self.message = await history_channel.send(embed=self.description())
        # self.message = await self.command_message.channel.send(embed=self.description())
        MatchMessage.MESSAGES[self.message.id] = self

        await self.command_message.delete()
        self.role_emojis = await EmojiHandler.role_emojis()

        # Add reactions for roles
        for emoji in EmojiHandler.ROLE_EMOJI_NAMES_SORTED:
            await self.message.add_reaction(self.role_emojis[emoji])


        # ping the user...
        ping = await history_channel.send(self.command_message.author.mention)
        await ping.delete()
        await self.command_message.channel.send(f'Started a new game in {history_channel.mention}!')

        # Set up reaction listeners
        def check(reaction, user):
            return (
                reaction.message.id == self.message.id
                and not user.bot
                and (hasattr(reaction.emoji, 'name') and reaction.emoji.name in self.role_emojis)
            )

        async def listen_for_reactions():
            while True:
                try:
                    add_task = asyncio.create_task(self.message.guild._state._get_client().wait_for('reaction_add', check=check))
                    remove_task = asyncio.create_task(self.message.guild._state._get_client().wait_for('reaction_remove', check=check))
                    done, pending = await asyncio.wait(
                        [add_task, remove_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in pending:
                        task.cancel()
                    for task in done:
                        reaction, user = task.result()
                        if task is add_task:
                            await self.on_react(reaction, user)
                        else:
                            await self.on_unreact(reaction, user)
                except Exception as e:
                    print(f"Error in reaction listener: {e}")
                    traceback.print_exc()
                    break

        asyncio.create_task(listen_for_reactions())
        asyncio.create_task(self.listen_for_match())

    async def listen_for_match(self):
        for _ in range(100):
            try:
                if len(self.players) < 10:
                    await asyncio.sleep(10)
                    continue

                # Get match from first player
                first_player = next(iter(self.players.values()))
                match_id = await first_player.get_current_match_id()

                if not match_id:
                    await asyncio.sleep(30)
                    continue

                # Get match data
                match_data = MatchData(match_id)
                await match_data.initialize()
                
                # Get participants
                participants = match_data.participants()
                
                # Count how many of our players are in this match
                player_count = 0
                for player in self.players.values():
                    if player.player_tag and player.player_tag in participants:
                        player_count += 1
                
                print(f"Found {player_count} players in match {match_id}")
                if player_count >= 6:  # If 6 or more of our players are in this match
                    print('Match found!')
                    self.match_data = match_data
                    # Update the match_id in the database
                    db_conn.store_match_message(
                        message_id=str(self.message.id),
                        match_id=match_id,
                        requesting_user_id=str(self.command_message.author.id),
                        requesting_user=str(self.command_message.author),
                        guild=str(self.command_message.guild.id)
                    )
                    await self.update_message()
                    return

            except Exception as e:
                print(f"Error in listen_for_match: {e}")
                traceback.print_exc()
                
            await asyncio.sleep(60)



    async def on_react(self, reaction, user):
        print('React')
        if reaction.emoji.name not in self.role_emojis:
            return

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

        print(f"Current preferences count: {len(self.player_preferences)}")
        print(f"Current players count: {len(self.players)}")
        print(f"Preferences: {self.player_preferences}")
        
        await self.update_message()
        if len(self.player_preferences) >= 10:
            print('Choosing roles!')
            self._choose_roles()
            self.timeout = 60*20 # 20 minutes
            await self.update_message()
        else:
            self.teams = {}

    async def on_unreact(self, reaction, user):
        print('Unreact')
        discord_user = str(user)
        if discord_user not in self.player_preferences:
            return
        
        # Fetch the message to get current reactions
        try:
            self.message = await self.message.channel.fetch_message(self.message.id)
            real_reaction_emoji = [r.emoji for r in self.message.reactions if r.emoji.name == reaction.emoji.name]
            if real_reaction_emoji:
                await self.message.remove_reaction(real_reaction_emoji[0], user)
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

        print(f"After unreact - preferences count: {len(self.player_preferences)}")
        print(f"After unreact - players count: {len(self.players)}")
        print(f"After unreact - preferences: {self.player_preferences}")

        await self.update_message()
        if len(self.player_preferences) >= 10:
            print('Choosing roles after unreact!')
            self._choose_roles()
            await self.update_message()
        else:
            self.teams = {}

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

        print('Chose roles! Best assignment:', best_assignment)
        self.teams = best_assignment  # May be None if no valid assignment



    def description(self):
        """
        There should be nothing async in this!!!
        Properties of the MatchMessage object should be fetched asynchronously
        Those properties should be read here, in the main thread
        """
        lines = [f'{discord_user:<{14}.{14}} : {' '.join(str(self.role_emojis[role]) for role in roles)}' for discord_user, roles in self.player_preferences.items()]
        embed = discord.Embed(
            title="League of Legends Lobby",
            description='',# '\n'.join(lines),
            color=discord.Color.blue()
        )
        embed.add_field(name='Users', value='\n'.join(lines[::2]), inline=True)
        embed.add_field(name='...', value='\n'.join(lines[1::2]), inline=True)
        embed.add_field(name='...', value='\n'.join(self.queued_players), inline=True)

        if self.match_data and self.match_data.completed:
            embed.set_footer(text='Game Complete!')
        else:
            embed.set_footer(text=f'Timeout: {self.timeout // 60}m {self.timeout % 60}s')

        if self.match_data is not None:
            if self.teams:
                _, _, lp_diff = self.teams
            else:
                lp_diff = '???'
            embed.add_field(name=f'Teams ({str(lp_diff)}LP diff)', value=str(self.match_data))

        # print("Teams data:", self.teams)
        elif self.teams:
            team_a, team_b, lp_diff = self.teams
            print("Team A:", team_a)
            print("Team B:", team_b)
            print("LP Diff:", lp_diff)

            col_left = [':black_square_button:' for _ in EmojiHandler.ROLE_EMOJI_NAMES_SORTED]
            col_right = [':black_square_button:' for _ in EmojiHandler.ROLE_EMOJI_NAMES_SORTED]
            col_mid = [f'`{team_a[role]:<{10}.{10}}` {self.role_emojis[role]} `{team_b[role]:>{10}.{10}}`' for role in EmojiHandler.ROLE_EMOJI_NAMES_SORTED]

            val = '\n'.join([' '.join([left, mid, right]) for left, mid, right in zip(col_left, col_mid, col_right)])
            embed.add_field(name=f'Teams ({lp_diff}LP diff)', value=val, inline=False)

        return embed

class MatchData:
    def __init__(self, match_id):
        self.match_id = match_id
        self.data = None  # Will hold the full match data after initialize
        self.completed = False

    async def initialize(self):
        """Fetch and cache match data from Riot API."""
        if self.data is not None:
            return  # Already initialized

        url = f"https://{RIOT_REGION}.api.riotgames.com/lol/match/v5/matches/{self.match_id}"
        headers = {'X-Riot-Token': RIOT_API_KEY}

        # Start background task to keep updating the data
        async def update_match_data():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status != 200:
                            raise Exception(f"Failed to fetch match data: {response.status}")
                        print(f'Updating data: {self.match_id}...')
                        self.data = await response.json()
                        self.completed = self.data['info']['endOfGameResult'].upper() == 'GameComplete'.upper()
                        # Store match data
                        db_conn.store_match(
                            match_id=self.match_id,
                            match_data=self.data
                        )
            except Exception as e:
                print(e)
                return
        
        async def task():
            for _ in range(100):
                try:
                    if self.completed:
                        return
                    await update_match_data()
                    await asyncio.sleep(30)
                except Exception as e:
                    print(e)
                    continue
                

        await update_match_data()
        asyncio.create_task(task())

    def participants(self):
        """Return a list of Summoner objects for each participant in the match."""
        if self.data is None:
            return {}
        participants_data = self.data['info']['participants']
        participants = [Summoner(p, self) for p in  participants_data]
        return { p.summoner_name : p for p in participants }

    async def summary(self):
        """Return a summary dictionary with key match info."""
        if self.data is None:
            await self.initialize()
        info = self.data['info']
        game_duration = info.get('gameDuration', 0)
        game_mode = info.get('gameMode', 'Unknown')
        teams = info.get('teams', [])
        # Find winning team
        winning_team = None
        for team in teams:
            if team.get('win'):
                winning_team = team
                break
        return {
            'game_duration': game_duration,
            'game_mode': game_mode,
            'winning_team': winning_team,
            'teams': teams,
        }

    def __str__(self):
        participants = list(self.participants().values())  # List[Summoner]

        team_ids = list(set(str(p.team_id) for p in participants))

        team_a, team_b = [[p for p in participants if str(p.team_id) == team_id] for team_id in team_ids]

        pad = max([len(SummonerProfile.SUMMONER_LOOKUP.get(p.summoner_name, p.summoner_name.split('#')[0])) for p in participants])
        summs_a = [f'`{SummonerProfile.SUMMONER_LOOKUP.get(p.summoner_name, p.summoner_name.split('#')[0]).ljust(pad, ' ')}`' for p in team_a]
        summs_b = [f'`{SummonerProfile.SUMMONER_LOOKUP.get(p.summoner_name, p.summoner_name.split('#')[0]).rjust(pad, ' ')}`' for p in team_b]

        emojis_a = [EmojiHandler.champion_emoji_by_id(p.champion_id) for p in team_a]
        emojis_b = [EmojiHandler.champion_emoji_by_id(p.champion_id) for p in team_b]

        kdas_a = [f'`{str(k).rjust(2, ' ')}/{str(d).rjust(2, ' ')}/{str(a).rjust(2, ' ')}`' for k, d, a in [p.kda() for p in team_a]]
        kdas_b = [f'`{str(k).rjust(2, ' ')}/{str(d).rjust(2, ' ')}/{str(a).rjust(2, ' ')}`' for k, d, a in [p.kda() for p in team_b]]

        emojis = [str(EmojiHandler._emojis[role]) for role in EmojiHandler.ROLE_EMOJI_NAMES_SORTED]


        zipped = zip(kdas_a, emojis_a, summs_a, emojis, summs_b, emojis_b, kdas_b)


        if self.completed:
            if bool(team_a[0].data['win']):
                description = ' '.join([f'`{' '*8}`', ':crown:', f'`{' '*pad}`', ':muscle:',  f'`{' '*pad}`', ':skull:', f'`{' '*8}`']) + '\n'
            else:
                description = ' '.join([f'`{' '*8}`', ':skull:', f'`{' '*pad}`', ':muscle:',  f'`{' '*pad}`', ':crown:', f'`{' '*8}`']) + '\n'
          
        description += '\n'.join([' '.join(z) for z in zipped]) + '\n'

        duration = (self.data['info']['gameEndTimestamp'] - self.data['info']['gameStartTimestamp']) // 1000
        lines = [
            f'Duration: {duration // 60}m {duration % 60 }s',
        ]


        description += '\n'.join(lines)

        return description

    def to_embed(self):
        embed_title = f"Match: {self.match_id}"
        embed = discord.Embed(
            title=embed_title,
            color=discord.Color.blue()
        )
        embed.add_field(name='Match Data', value=str(self))

        return embed



if __name__ == '__main__':
    async def fun():
        await EmojiHandler.initialize()

        match_id = 'NA1_5285712809'
        data = MatchData(match_id)
        await data.initialize()
        # print(asyncio.run(p.get_profile_summary()))
        participants = data.participants()
        champid = participants[0].champion_id


        emoji = EmojiHandler.champion_emoji_by_id(champid)

        print(emoji.name)
    
    asyncio.run(fun())