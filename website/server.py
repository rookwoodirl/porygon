from flask import Flask
from flask import Flask, render_template, redirect
import os, random, requests

import typeracer


app = Flask(__name__)

def randomWord(count=1):
    """
    generate random combinations for instancing things
    """
    with open(os.path.join('assets', 'convenience', 'randomwords.txt')) as f:
        words = f.readlines()
        return ''.join([random.choice(words).replace('\n', '') for _ in range(count)])


@app.route('/')
def home():
    return render_template('homepage.html')

@app.route('/dev')
def dev():
    from webobject import HoverPanel, Grid
    panel = HoverPanel('typeracer', 'typeracer.svg', redirect='typeracer')

    obj = Grid([panel.html] * 6, width='30%', height='80%')

    return obj.html
    
    f"""
        <div style="display: flex; width: 30%; height: 80%; justify-content: center; align-items: center;">
            {obj.html}
        </div>
    """

@app.route('/typeracer')
def typeracer_home():
    word = randomWord(3)
    while word in typeracer.games:
        word = randomWord(3)
    return redirect(f'/typeracer/{word}')

@app.route('/typeracer/<gameid>')
def typeracer_html(gameid):
    return typeracer.get_game(gameid).html()

@app.route('/typeracer/<gameid>/new-prompt')
def typeracer_new_prompt(gameid):
    """
    make the ${gameid} select a new prompt
    """
    return { 'prompt' : typeracer.get_game(gameid).new_prompt() }

@app.route('/typeracer/<gameid>/prompt')
def typeracer_prompt(gameid):
    """
    get the name of the text file for ${gameid}
    """
    return { 'prompt' : typeracer.get_game(gameid).prompt }

@app.route('/typeracer/prompt/<prompt>')
def typeracer_prompt_definition(prompt):
    """
    get the full text of ${prompt}
    """
    return { 'prompt' : typeracer.prompts[prompt] }

@app.route('/typeracer/<gameid>/get-scores')
def typeracer_scores(gameid):
    return typeracer.get_game(gameid).get_scores()
    

@app.route('/typeracer/<gameid>/submit-score/<player>/<time>/<wpm>')
def typeracer_submit_score(gameid, player, time, wpm):
    return typeracer.get_game(gameid).submit_score(player, time, wpm)

@app.route('/randomChamp')
def randomChamp():
    champs = requests.get('https://ddragon.leagueoflegends.com/cdn/14.20.1/data/en_US/champion.json')
    champs = list(champs.json()['data'].keys())
    return random.choice(champs)

    



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