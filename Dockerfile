FROM python:3.9-slim-buster
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY templates/ templates/
COPY static/ static/ # Pastikan folder static ada dan berisi style_minimal.css & script_minimal.js
ENV PORT=5000 
EXPOSE 5000
CMD ["python", "app.py"]
