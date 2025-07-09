import os
from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello_world():
    return "Hello, Railway! This is a working app."

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
