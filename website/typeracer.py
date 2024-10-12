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
        self.prompt = self.get_prompt()

        games[gameid] = self

    def html(self):
        return render_template('typeracer.html', prompt=self.prompt, player='me', gameid=self.gameid)

    def get_scores(self):
        with self.lock:
            return self.data

    def new_prompt(self):
        prompts = os.listdir(DIR_PROMPTS)

        with open(os.path.join(DIR_PROMPTS, random.choice(prompts))) as f:
            self.prompt = ' '.join(f.readlines())

        self.prompt = self.new_prompt()
        self.data['hash'] = str(hash(self.prompt))[:8]

    def get_prompt(self):
        return self.prompt


    def submit_score(self, player, time, wpm, promptHash):
        
        with self.lock: # lock the data file
            self.data[player.replace(' ', '_')] = {
                'player' : player,
                'time' : time,
                'wpm' : wpm,
                'hash' : promptHash
            }
            with open(os.path.join(DIR_SCOREBOARDS, f'{self.gameid}.csv'), 'w+') as f:
                f.write('\n'.join([','.join([player, self.data[player]['time'], self.data[player]['wpm']]) for player in self.data]))

        return 'ok'