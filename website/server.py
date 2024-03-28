from flask import Flask
from flask import Flask, render_template
import os


app = Flask(__name__)

@app.route('/')
def home():
    return 'ur very cute :3'

@app.route('/notecards/<name>')
def notecards(name):
    print('awooga')
    with open(os.path.join('assets', 'notecards', f'{name}.csv')) as f:
        notecards_data = {}
        for line in f.readlines():
            k, v = line.split(',')
            notecards_data[k] = v

    # shuffle
    items = list(notecards_data.items())
    random.shuffle(items)
    notecards_data = dict(items)

    return render_template('notecards.html', notecards_data=notecards_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)



import random



# Sample dictionary
my_dict = {'a': 1, 'b': 2, 'c': 3, 'd': 4}


def shuffle(my_dict):
    
    return random_dict