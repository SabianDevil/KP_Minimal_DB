FROM python:3.9-slim-buster
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
# --- PERBAIKAN DI SINI ---
# Pastikan PORT tersetel (komentar ini di baris terpisah)
ENV PORT=5000 
# --- AKHIR PERBAIKAN ---
EXPOSE 5000
CMD ["python", "app.py"]
