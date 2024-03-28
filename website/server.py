from flask import Flask
from flask import Flask, render_template
import os, random


app = Flask(__name__)

@app.route('/')
def home():
    return 'ur very cute :3'

@app.route('/flashcards/<name>')
def flashcards(name):
    print('awooga')
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)



import random



# Sample dictionary
my_dict = {'a': 1, 'b': 2, 'c': 3, 'd': 4}


def shuffle(my_dict):
    
    return random_dict