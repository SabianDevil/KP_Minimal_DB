import os
from flask import Flask, request, jsonify, render_template
from sqlalchemy import create_engine, Column, String, DateTime, Integer
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import pytz 
import uuid # Diperlukan untuk ID User

# --- INISIALISASI APLIKASI FLASK ---
app = Flask(__name__)

# --- KONFIGURASI DATABASE RAILWAY POSTGRESQL INTERNAL ---
# Railway akan otomatis menyuntikkan DATABASE_URL untuk PostgreSQL internalnya
DATABASE_URL = os.getenv("DATABASE_URL")

# --- DEBUGGING PENTING ---
# Baris ini akan mencetak nilai DATABASE_URL ke log Railway Anda saat aplikasi dimulai.
print(f"DEBUG: DATABASE_URL yang diterima: '{DATABASE_URL}'") 
if not DATABASE_URL:
    print("ERROR: DATABASE_URL is None or empty. Please ensure Railway's PostgreSQL Add-on is attached to this service.")
    raise ValueError("DATABASE_URL environment variable not set for Railway PostgreSQL.")
# --- AKHIR DEBUGGING ---

try:
    engine = create_engine(DATABASE_URL)
    # Coba koneksi segera setelah engine dibuat
    with engine.connect() as connection:
        print("INFO: Database connection engine created and tested successfully.")
        
        # Definisikan Base di sini sebelum memanggil create_all
        Base = declarative_base() 
        
        # --- MODEL BARU: TABEL USERS ---
        class User(Base):
            __tablename__ = 'users'
            # id akan di-generate oleh Python karena default=lambda
            id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())) 
            username = Column(String, unique=True, nullable=False)
            password_hash = Column(String, nullable=False) # Tidak aman untuk produksi, hanya untuk tes
            email = Column(String, unique=True, nullable=False)
            created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

            def to_dict(self):
                return {
                    "id": self.id,
                    "username": self.username,
                    "email": self.email,
                    "created_at": self.created_at.isoformat() if self.created_at else None
                }
        
        # Coba buat tabel users jika belum ada
        Base.metadata.create_all(connection) 
        print("INFO: User table created or already exists.")
except Exception as e:
    print(f"FATAL ERROR: Failed to create database engine or connect, or create tables: {e}")
    # Jangan raise error di sini agar aplikasi Flask bisa start dan menampilkan status
    # Ini penting untuk tujuan debugging agar kita bisa melihat apa yang terjadi di browser
    pass # Lanjutkan eksekusi meskipun database bermasalah

Session = sessionmaker(bind=engine) 

# --- KONFIGURASI ZONA WAKTU (Diperlukan oleh datetime.utcnow untuk created_at) ---
# Di Railway, waktu server biasanya UTC. Kita pakai UTC untuk konsistensi DB.
LOCAL_TIMEZONE = pytz.timezone('UTC') 


# --- Routes Aplikasi Minimalis ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register_user():
    session = Session()
    try:
        data = request.json
        username = data.get('username')
        email = data.get('email')
        password = data.get('password') 

        if not username or not email or not password:
            return jsonify({"error": "Username, email, dan password diperlukan"}), 400

        existing_user = session.query(User).filter_by(username=username).first()
        if existing_user:
            return jsonify({"error": "Username sudah terdaftar"}), 409 
        
        existing_user_email = session.query(User).filter_by(email=email).first()
        if existing_user_email:
            return jsonify({"error": "Email sudah terdaftar"}), 409 

        new_user = User(
            username=username,
            password_hash=password, 
            email=email
        )
        session.add(new_user)
        session.commit()
        return jsonify({"message": "Registrasi berhasil!", "user": new_user.to_dict()}), 201
    except Exception as e:
        session.rollback()
        print(f"FATAL ERROR in register_user: {e}")
        return jsonify({"error": f"Terjadi kesalahan server saat registrasi: {str(e)}"}), 500
    finally:
        session.close()

@app.route('/login', methods=['POST'])
def login_user():
    session = Session()
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password') 

        if not username or not password:
            return jsonify({"error": "Username dan password diperlukan"}), 400

        user = session.query(User).filter_by(username=username).first()
        if not user or user.password_hash != password: 
            return jsonify({"error": "Username atau password salah"}), 401 
        
        return jsonify({"message": "Login berhasil!", "user": user.to_dict()}), 200
    except Exception as e:
        print(f"FATAL ERROR in login_user: {e}")
        return jsonify({"error": f"Terjadi kesalahan server saat login: {str(e)}"}), 500
    finally:
        session.close()

@app.route('/get_all_users', methods=['GET'])
def get_all_users():
    session = Session()
    try:
        users = session.query(User).all()
        return jsonify([user.to_dict() for user in users]), 200
    except Exception as e:
        print(f"FATAL ERROR in get_all_users: {e}")
        return jsonify({"error": f"Terjadi kesalahan server saat mengambil user: {str(e)}"}), 500
    finally:
        session.close()

# --- Bagian untuk menjalankan Flask App ---
if __name__ == '__main__':
    # Ambil PORT dari environment yang disediakan Railway, default ke 5000
    port = int(os.getenv("PORT", 5000))
    print(f"INFO: Flask app running on port {port}")
    app.run(debug=True, host='0.0.0.0', port=port)
