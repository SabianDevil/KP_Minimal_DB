from flask import Flask, render_template, send_from_directory

# Mengkonfigurasi Flask untuk mencari templates dan static files di root folder
app = Flask(__name__,
            template_folder='.',  # Mencari templates di folder saat ini (root)
            static_folder='.')    # Mencari static files di folder saat ini (root)

@app.route('/')
def hello():
    # Merender index.html yang berada di root folder
    return render_template('index.html')

# Flask secara default tidak akan menyajikan file CSS/JS dari root folder
# Kita perlu menambahkan rute khusus untuk melayani file-file ini
@app.route('/style.css')
def serve_css():
    return send_from_directory('.', 'style.css')

@app.route('/script.js')
def serve_js():
    return send_from_directory('.', 'script.js')

if __name__ == '__main__':
    app.run(debug=True)
