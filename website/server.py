from flask import Flask
from flask import Flask, render_template
import os, random

import typeracer


app = Flask(__name__)
typeracerLocks = {}


@app.route('/')
def home():
    return 'pory... is... alive!!!'

@app.route('/typeracer/<gameid>/<player>')
def typeracer_html(gameid, player):
    return typeracer.get_game(gameid).html(player)


@app.route('/typeracer/<gameid>/get-scores')
def typeracer_scores(gameid):
    return typeracer.get_game(gameid).get_scores()
    

@app.route('/typeracer/<gameid>/submit-score/<player>/<time>/<wpm>')
def typeracer_submit_score(gameid, player, time, wpm):
    return typeracer.get_game(gameid).submit_score(player, time, wpm)

    



@app.route('/flashcards/<name>')
def flashcards(name):
    with open(os.path.join('assets', 'flashcards', f'{name}.csv')) as f:
        flashcards_data = {}
        for line in f.readlines():
            k, v = line.split(',')
            flashcards_data[k] = v

    # shuffle
    items = list(flashcards_data.items())
    random.shuffle(items)
    flashcards_data = dict(items)

    return render_template('flashcards.html', flashcards_data=flashcards_data)


for convenience in ['sp500']:
    @app.route(f'/{convenience}')
    def fun():
        with open(os.path.join('assets', 'convenience', f'{convenience}.csv')) as f:
            return '<pre>' + ''.join(f.readlines()) + '</pre>'


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)