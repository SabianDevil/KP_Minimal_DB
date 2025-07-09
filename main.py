from flask import Flask, render_template, send_from_directory

app = Flask(__name__,
            template_folder='.',  # Mencari templates di folder saat ini (root)
            static_folder='.')    # Mencari static files di folder saat ini (root)

@app.route('/')
def hello():
    return render_template('index.html')

@app.route('/style.css')
def serve_css():
    return send_from_directory('.', 'style.css')

@app.route('/script.js')
def serve_js():
    return send_from_directory('.', 'script.js')
