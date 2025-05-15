import os
import aiohttp
from typing import List, Dict, Optional
from dotenv import load_dotenv
import asyncio
import discord

load_dotenv()
bot = None # this is set by main.py

RIOT_API_KEY = os.getenv('RIOT_API_KEY')
RIOT_API_BASE = 'https://na1.api.riotgames.com'
RIOT_REGION = 'americas'
DDRAGON_VERSION = '13.24.1'

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
        )
        self.team_id = participant.get('teamId')
        self.win = participant.get('win', False)
        self.kills = participant.get('kills', 0)
        self.deaths = participant.get('deaths', 0)
        self.assists = participant.get('assists', 0)
        self.champion_level = participant.get('champLevel', 0)
        self.total_damage_dealt = participant.get('totalDamageDealtToChampions', 0)
        self.vision_score = participant.get('visionScore', 0)
        self.gold_earned = participant.get('goldEarned', 0)

    def kda(self):
        return (self.kills, self.deaths, self.assists)

    def kda_ratio(self) -> float:
        if self.deaths == 0:
            return self.kills + self.assists
        return (self.kills + self.assists) / self.deaths

class SummonerProfile:
    """
    Represents the out-of-game profile of a League of Legends player
    Includes functions that do API calls for:
        profile summary
        match history
        mastery points
    Can optionally be associated with a Discord user's profile
    """
    def __init__(self, player_tag: str, discord_name: Optional[str] = None):
        self.player_tag = player_tag  # Player#NA1
        self.discord_name = discord_name
        self._puuid = None
        self._summoner_id = None
        self._account_id = None

    async def _get_puuid(self) -> str:
        """Get PUUID from Riot ID"""
        if self._puuid:
            return self._puuid

        game_name, tag_line = self.player_tag.split('#')
        url = f'https://{RIOT_REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}'
        headers = {'X-Riot-Token': RIOT_API_KEY}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get PUUID: {response.status}")
                data = await response.json()
                self._puuid = data['puuid']
                return self._puuid

    async def _get_summoner_data(self) -> Dict:
        """Get basic summoner data using PUUID"""
        if not self._puuid:
            await self._get_puuid()

        url = f'{RIOT_API_BASE}/lol/summoner/v4/summoners/by-puuid/{self._puuid}'
        headers = {'X-Riot-Token': RIOT_API_KEY}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get summoner data: {response.status}")
                return await response.json()

    async def mastery(self) -> List[Dict]:
        """Get champion mastery data"""
        if not self._puuid:
            await self._get_puuid()

        url = f'{RIOT_API_BASE}/lol/champion-mastery/v4/champion-masteries/by-puuid/{self._puuid}'
        headers = {'X-Riot-Token': RIOT_API_KEY}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get mastery data: {response.status}")
                return await response.json()

    async def match_history(self, limit: int = 10) -> List[str]:
        """Get recent match IDs"""
        if not self._puuid:
            await self._get_puuid()

        url = f'https://{RIOT_REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{self._puuid}/ids'
        params = {'start': 0, 'count': limit}
        headers = {'X-Riot-Token': RIOT_API_KEY}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get match history: {response.status}")
                return await response.json()

    async def profile_summary(self) -> Dict:
        """Get comprehensive profile summary including rank and stats"""
        summoner_data = await self._get_summoner_data()
        self._summoner_id = summoner_data['id']

        # Get ranked data
        url = f'{RIOT_API_BASE}/lol/league/v4/entries/by-summoner/{self._summoner_id}'
        headers = {'X-Riot-Token': RIOT_API_KEY}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get ranked data: {response.status}")
                ranked_data = await response.json()

        # Get top 3 champions by mastery
        mastery_data = await self.mastery()
        top_champs = sorted(mastery_data, key=lambda x: x['championPoints'], reverse=True)[:3]

        # Get profile picture emoji
        profile_icon_id = summoner_data.get('profileIconId')
        profile_picture = await EmojiHandler.summoner_profile_picture(str(profile_icon_id)) if profile_icon_id else None

        return {
            'summoner': summoner_data,
            'ranked': ranked_data,
            'top_champions': top_champs,
            'profile_picture': f':{profile_picture.name}:'
        }

    async def get_current_match(self) -> Optional[Dict]:
        """Get current game data if the player is in a game"""
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
                return await response.json()
    


class MatchData:
    def __init__(self, match_id):
        self.match_id = match_id
        self.data = None  # Will hold the full match data after initialize

    async def initialize(self):
        """Fetch and cache match data from Riot API."""
        if self.data is not None:
            return  # Already initialized

        url = f"https://{RIOT_REGION}.api.riotgames.com/lol/match/v5/matches/{self.match_id}"
        headers = {'X-Riot-Token': RIOT_API_KEY}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch match data: {response.status}")
                self.data = await response.json()

    async def participants(self):
        """Return a list of Summoner objects for each participant in the match."""
        if self.data is None:
            await self.initialize()
        participants_data = self.data['info']['participants']
        return [Summoner(p, self) for p in participants_data]

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

    async def to_embed(self):
        embed_title = "Lane Matchups"
        embed = discord.Embed(
            title=embed_title,
            color=discord.Color.blue()
        )


        participants = await self.participants()  # List[Summoner]


        pad = max([len(p.summoner_name) for p in participants])+1
        roles = list((await EmojiHandler.role_emojis()).values())
        lines = []
        for player1, player2, role in zip(participants[:5], participants[5:], roles):

            champ1_emoji = await EmojiHandler.champion_emoji_by_id(player1.champion_id)
            champ2_emoji = await EmojiHandler.champion_emoji_by_id(player2.champion_id)

            kda1 = '/'.join([str(i) for i in player1.kda()])
            kda2 = '/'.join([str(i) for i in player2.kda()])

            line = f'`{kda1:>{11}.{11}}` {champ1_emoji} `{player1.summoner_name:>{pad}.{pad}}` {role} `{player2.summoner_name:<{pad}.{pad}}` {champ2_emoji} `{kda2:<{11}.{11}}`'

            lines.append(line)

        embed.add_field(name='Matchups', value='\n'.join(lines))
        return embed

class EmojiHandler:
    _champion_data = None

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
    async def champion_id_to_name(cls, champion_id: str) -> str:
        """Convert a champion ID to the champion name"""
        await cls._init_champion_data()
        return cls._champion_data.get(str(champion_id), f"Unknown Champion {champion_id}")

    @classmethod
    async def champion_emoji_by_id(cls, champion_id: str):
        """Get champion emoji by ID"""
        champion_name = await cls.champion_id_to_name(champion_id)
        return await cls.champion_emoji_by_name(champion_name)

    @classmethod
    async def champion_emoji_by_name(cls, champion_name: str):
        """Get champion emoji by name"""
        emojis = {str(emoji.name): emoji for emoji in await bot.fetch_application_emojis()}
        champion_name = champion_name.replace(' ', '').replace('.', '')

        if champion_name in emojis:
            return emojis[champion_name]
        else:
            # Get champion icon from Data Dragon
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

    @classmethod
    async def role_emojis(cls):
        return { str(emoji.name) : emoji for emoji in await bot.fetch_application_emojis() if str(emoji.name) in ['TOP', 'JGL', 'MID', 'BOT', 'SUP']}




if __name__ == '__main__':
    p = SummonerProfile('hero#rook', discord_name='rookwood')

    print(asyncio.run(p.profile_summary()))

    