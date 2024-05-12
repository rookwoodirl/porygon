from flask import Flask
from flask import Flask, render_template
import os, random


app = Flask(__name__)

@app.route('/')
def home():
    return 'pory... is... alive!!!'

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
        with open(os.path.join('convenience', f'{convenience}.csv')) as f:
            return '\n'.join(f.readlines())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)