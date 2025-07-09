FROM python:3.9-slim-buster
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt # Ini akan menginstal dependency jika ada
COPY app.py .
ENV PORT=8000 # Set PORT ke 8000
EXPOSE 8000 # Expose PORT 8000
CMD ["python", "app.py"]
