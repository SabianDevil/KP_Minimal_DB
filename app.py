import os
from flask import Flask, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import text as sa_text # Diperlukan untuk Base.metadata.create_all

app = Flask(__name__)

# --- KONFIGURASI DATABASE RAILWAY POSTGRESQL INTERNAL ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- DEBUGGING PENTING ---
print(f"DEBUG: DATABASE_URL yang diterima: '{DATABASE_URL}'") 
if not DATABASE_URL:
    print("ERROR: DATABASE_URL is None or empty. Please ensure Railway's PostgreSQL Add-on is attached.")
    raise ValueError("DATABASE_URL environment variable not set for Railway PostgreSQL.")

try:
    engine = create_engine(DATABASE_URL)
    # Coba koneksi segera setelah engine dibuat
    with engine.connect() as connection:
        print("INFO: Database connection engine created and tested successfully.")
        # Definisikan model minimal untuk membuat tabel jika belum ada
        Base = declarative_base()
        class TestTable(Base):
            __tablename__ = 'test_connection_table'
            id = Column(Integer, primary_key=True)
            message = Column(String)
        Base.metadata.create_all(connection) # Coba buat tabel test
        print("INFO: Test table created or already exists.")
    db_status = "Connected successfully!"
except Exception as e:
    print(f"FATAL ERROR: Failed to create database engine or connect: {e}")
    db_status = f"Connection failed: {str(e)}"
    # Jangan raise error di sini agar aplikasi Flask bisa start dan menampilkan status
    # Kita ingin melihat apa yang terjadi di browser

Session = sessionmaker(bind=engine) # Session dan Base tetap diperlukan untuk model

@app.route('/')
def index():
    return f"Database status: {db_status}"

@app.route('/health')
def health_check():
    return jsonify({"status": "ok", "db_check": db_status})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=os.getenv("PORT", 5000))
