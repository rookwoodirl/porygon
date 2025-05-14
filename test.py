from commands.newgame import Player, MatchData
import asyncio



async def test():
    p = Player('rookwood')
    await p.initialize()
    print(p.puuid)
    match_id = await p.get_most_recent_match_id()
    print(match_id)

    m = MatchData(match_id)
    await m.initialize()

    s = await m.summoners()
    print(s[0].champion)


asyncio.run(test())
