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

    return render_template('notecards.html', notecards_data=notecards_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)