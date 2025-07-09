from flask import Flask, render_template, send_from_directory
import os

# Mengkonfigurasi Flask untuk mencari templates dan static files di root folder
# os.getcwd() akan mengembalikan direktori kerja kontainer /app
current_dir = os.getcwd()
app = Flask(__name__,
            template_folder=current_dir,  # Mencari templates di folder saat ini (root /app)
            static_folder=current_dir)    # Mencari static files di folder saat ini (root /app)

@app.route('/')
def hello():
    # Merender index.html yang berada di root folder
    return render_template('index.html')

# Flask secara default tidak akan menyajikan file CSS/JS dari root folder
# Kita perlu menambahkan rute khusus untuk melayani file-file ini
@app.route('/style.css')
def serve_css():
    # Menggunakan current_dir untuk memastikan path absolut di dalam kontainer
    return send_from_directory(current_dir, 'style.css')

@app.route('/script.js')
def serve_js():
    # Menggunakan current_dir untuk memastikan path absolut di dalam kontainer
    return send_from_directory(current_dir, 'script.js')

if __name__ == '__main__':
    # Untuk pengujian lokal tanpa Gunicorn
    # Di Railway, Gunicorn akan menjalankan aplikasi dan mengabaikan bagian ini.
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
