FROM python:3.9-slim-buster
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY startup.sh .
# --- PERBAIKAN DI SINI ---
# PORT ini tidak terlalu relevan untuk skrip non-web, tapi biarkan saja (komentar di baris terpisah)
ENV PORT=5000 
# --- AKHIR PERBAIKAN ---
EXPOSE 5000
CMD ["/bin/bash", "startup.sh"]
