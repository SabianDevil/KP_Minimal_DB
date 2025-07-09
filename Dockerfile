FROM python:3.9-slim-buster
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 
COPY app.py .
# --- PERBAIKAN DI SINI ---
# Komentar ini sekarang di baris terpisah
ENV PORT=8000 
# --- AKHIR PERBAIKAN ---
EXPOSE 8000
CMD ["python", "app.py"]
