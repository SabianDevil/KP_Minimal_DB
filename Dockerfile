# Gunakan image Python resmi sebagai base image
FROM python:3.9-slim-buster

# Tetapkan direktori kerja di dalam kontainer
WORKDIR /app

# Salin file requirements.txt ke direktori kerja
COPY requirements.txt .

# Instal dependensi Python
RUN pip install --no-cache-dir -r requirements.txt

# Unduh model SpaCy secara terpisah
# Model Bahasa Indonesia (dikomentari karena error):
# RUN python -m spacy download id_core_news_sm
# Model Bahasa Inggris (aktifkan):
RUN python -m spacy download en_core_web_sm

# Salin semua file lainnya ke direktori kerja kontainer
COPY . .

# Inisialisasi database saat build Docker (membuat reminders.db)
RUN python database.py

# Beri tahu Docker bahwa kontainer akan mendengarkan di port ini
EXPOSE $PORT

# Perintah untuk menjalankan aplikasi saat kontainer dimulai
CMD gunicorn app:app --bind 0.0.0.0:"$PORT"
