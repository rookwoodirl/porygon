import json, threading, os
from flask import Flask, render_template
import random

DIR_TYPERACER = os.path.join('assets', 'typeracer')
DIR_PROMPTS = os.path.join(DIR_TYPERACER, 'prompts')
DIR_SCOREBOARDS = os.path.join(DIR_TYPERACER, 'scoreboard')


games = {}

def get_game(gameid):
    if gameid not in games:
        games[gameid] = TyperacerGame(gameid)

    return games[gameid]


class TyperacerGame:

    data = {}
    
    def __init__(self, gameid):
        self.gameid = gameid
        self.lock = threading.Lock()

    def html(self, player):
        return render_template('typeracer.html', prompt=self.prompt(), player=player)

    def get_scores(self):
        with self.lock:
            return [self.data[player] for player in self.data]

    def prompt(self):
        prompts = os.listdir(DIR_PROMPTS)

        with open(os.path.join(DIR_PROMPTS, random.choice(prompts))) as f:
            return ' '.join(f.readlines())


    def submit_score(self, player, wpm, time):
        
        with self.lock: # lock the data file
            self.data[player] = {
                'player' : player,
                'wpm' : wpm, 
                'time' : time
            }
            with open(os.path.join(DIR_SCOREBOARDS, f'{self.gameid}.csv'), 'w+') as f:
                f.write('\n'.join([','.join([player, self.data[player]['wpm'], self.data[player]['time']]) for player in self.data]))

        return 'ok'