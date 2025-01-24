from flask import Flask

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def receive_message():
    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8088) 