FROM python:3.9-slim-buster
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py . # Pastikan ini main.py, bukan app.py
COPY startup.sh . # Salin skrip startup.sh
ENV PORT=5000 # PORT ini tidak terlalu relevan untuk skrip non-web, tapi biarkan saja
EXPOSE 5000 # Tidak relevan untuk skrip non-web
CMD ["/bin/bash", "startup.sh"] # <<< PERUBAHAN PENTING DI SINI
