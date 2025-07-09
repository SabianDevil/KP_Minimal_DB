# Gunakan image Python resmi sebagai base image
FROM python:3.9-slim-buster

# Tetapkan direktori kerja di dalam kontainer
WORKDIR /app

# Salin file requirements.txt ke direktori kerja
COPY requirements.txt .

# Instal dependensi Python
RUN pip install --no-cache-dir -r requirements.txt

# Salin semua file lainnya ke direktori kerja kontainer
# Ini akan menyalin app.py, Dockerfile, index.html, style.css, script.js, database.py
COPY . .

# Inisialisasi database saat build Docker (membuat reminders.db)
RUN python database.py

# Beri tahu Docker bahwa kontainer akan mendengarkan di port ini
EXPOSE $PORT

# Perintah untuk menjalankan aplikasi saat kontainer dimulai
# Menggunakan bentuk shell CMD untuk memastikan $PORT diinterpretasikan
CMD gunicorn app:app --bind 0.0.0.0:"$PORT"
