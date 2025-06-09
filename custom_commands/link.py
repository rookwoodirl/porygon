import discord
from discord.ext import commands
import os
import aiohttp
import json
from dotenv import load_dotenv
from utils.postgres import RiotPostgresManager

load_dotenv()

RIOT_API_KEY = os.getenv('RIOT_API_KEY')
RIOT_API_BASE = 'https://na1.api.riotgames.com'
CHAMPION_DATA_URL = 'http://ddragon.leagueoflegends.com/cdn/13.24.1/data/en_US/champion.json'

# Initialize database connection
db_conn = RiotPostgresManager()

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

async def get_summoner_data(session, summoner_name, tag):
    # First get the PUUID using the Riot Account API
    account_url = f'https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{summoner_name}/{tag}'
    headers = {'X-Riot-Token': RIOT_API_KEY}
    
    async with session.get(account_url, headers=headers) as response:
        if response.status == 404:
            return None, "Summoner not found"
        if response.status != 200:
            return None, f"Error fetching account: {response.status}"
        
        account_data = await response.json()
        puuid = account_data['puuid']
    
    # Get summoner data using PUUID
    summoner_url = f'{RIOT_API_BASE}/lol/summoner/v4/summoners/by-puuid/{puuid}'
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
        'mastery': mastery_data,
        'puuid': puuid
    }, None

def format_ranked_data(ranked_data):
    if not ranked_data:
        return "Unranked"
    
    # Find solo queue data
    solo_queue = next((q for q in ranked_data if q['queueType'] == 'RANKED_SOLO_5x5'), None)
    if not solo_queue:
        return "Unranked"
    
    return f"{solo_queue['tier']} {solo_queue['rank']} {solo_queue['leaguePoints']} LP"

async def format_mastery_data(mastery_data):
    top_champs = sorted(mastery_data, key=lambda x: x['championPoints'], reverse=True)[:3]
    champ_names = []
    for champ in top_champs:
        name = await get_champion_name(champ['championId'])
        points = champ['championPoints']
        champ_names.append(f"{name} ({points:,} pts)")
    return ", ".join(champ_names)

async def link(ctx, *, summoner_input):
    """
    Link your Discord account with your League of Legends account.
    Usage: !link <summoner_name#tag>
    Example: !link Doublelift#NA1
    """
    if not RIOT_API_KEY:
        await ctx.send("Riot API key not configured. Please contact an administrator.")
        return

    try:
        # Parse summoner name and tag
        if '#' not in summoner_input:
            await ctx.send("Please provide your summoner name in the format: name#tag")
            return
        
        summoner_name, tag = summoner_input.split('#', 1)
        
        async with aiohttp.ClientSession() as session:
            data, error = await get_summoner_data(session, summoner_name, tag)
            if error:
                await ctx.send(error)
                return
            
            # Store in PostgreSQL database
            try:
                db_conn.store_summoner(str(ctx.author), summoner_name, tag, data['puuid'])
            except Exception as e:
                await ctx.send(f"Error storing summoner data: {str(e)}")
                return
            
            # Create embed
            embed = discord.Embed(
                title=f"Summoner Profile: {summoner_name}",
                color=discord.Color.blue()
            )
            
            # Add profile icon
            profile_icon_url = f"http://ddragon.leagueoflegends.com/cdn/13.24.1/img/profileicon/{data['summoner']['profileIconId']}.png"
            embed.set_thumbnail(url=profile_icon_url)
            
            # Add ranked info
            ranked_info = format_ranked_data(data['ranked'])
            embed.add_field(name="Rank", value=ranked_info, inline=True)
            
            # Add level
            embed.add_field(name="Level", value=str(data['summoner']['summonerLevel']), inline=True)
            
            # Add top champions
            top_champs = await format_mastery_data(data['mastery'])
            embed.add_field(name="Top Champions", value=top_champs, inline=False)
            
            await ctx.send(embed=embed)
            
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

async def run(ctx):
    """
    Link your Discord account with your League of Legends account.
    Usage: !link <summoner_name#tag>
    Example: !link Doublelift#NA1
    """
    try:
        # Get the full message content and remove the command
        content = ctx.message.content
        command_length = len('!link')
        summoner_input = content[command_length:].strip()
        
        if not summoner_input:
            await ctx.send("Please provide your summoner name in the format: name#tag")
            return
            
        await link(ctx, summoner_input=summoner_input)
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
