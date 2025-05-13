def run():
    # TODO: 
    pass

ROLE_EMOTES = ['TOP', 'JGL', 'MID', 'BOT', 'SUP']
TEAM_EMOTES = ['TEAM_RED', 'TEAM_BLUE']

class Player:
    def __init__(self, discord_name):
        self.discord_name = discord_name

class Match:
    preferred_roles = { role : [] for role in ROLE_EMOTES }
    players = { team : { role : None for role in ROLE_EMOTES } for team in TEAM_EMOTES }

    def roles_dfs(self):
        # TODO: 
        #   Players can queue for multiple roles by reacting to the post.
        #   Find a combination of players so everyone gets a preferred role.
        #   If a player is queued for multiple teams, they can only be finally assigned to 1 team
        #   If not every role can be filled, just keep it empty.
        #   Update players dict with new roles
        pass

    def description(self):
        return '\n'.join([f'{self.players[TEAM_EMOTES[0]][role]} :{role}: {self.players[TEAM_EMOTES[1]][role]}' for role in ROLE_EMOTES])

    def on_react(reaction):
        if reaction not in ROLE_EMOTES or TEAM_EMOTES:
            return

        # TODO:
        #   Add player to the team they reacted with their preferred role
        #   Update preferred_roles
        #   Players can react for both teams but only ultimately end up on 1
        

def new_game():
    """
    !newgame 
    Posts to #lol-queue. Creates channel if it does not exist.
    Reacts to itself with each of ROLE_EMOTES and TEAM_EMOTES, to start the poll
    Distributes players to Team A and Team B, giving players one of their preferred roles
    """