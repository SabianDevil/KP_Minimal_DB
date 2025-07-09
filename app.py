import os
from flask import Flask, request, jsonify, render_template
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Integer
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import pytz # Masih diperlukan karena LOCAL_TIMEZONE

# --- INISIALISASI APLIKASI FLASK ---
app = Flask(__name__)

# --- KONFIGURASI DATABASE RAILWAY POSTGRESQL INTERNAL ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- DEBUGGING PENTING ---
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
except Exception as e:
    print(f"FATAL ERROR: Failed to create database engine or connect: {e}")
    # Jika gagal konek di awal, hentikan aplikasi agar tidak crash terus-menerus
    raise e 

Session = sessionmaker(bind=engine)
Base = declarative_base()

# --- KONFIGURASI ZONA WAKTU (Diperlukan oleh datetime.now(LOCAL_TIMEZONE)) ---
LOCAL_TIMEZONE = datetime.now(pytz.utc).astimezone().tzinfo

# --- MODEL DATABASE (Hanya User) ---
class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4())) # Gunakan uuid di Python untuk ID
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False) # Kita tidak akan implementasi hash password kompleks
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __repr__(self):
        return f"<User(id='{self.id}', username='{self.username}', email='{self.email}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

# --- Import uuid untuk pembuatan ID User ---
import uuid

# --- Routes Aplikasi Minimalis ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register_user():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password') # Password mentah, tidak aman untuk produksi

    if not username or not email or not password:
        return jsonify({"error": "Username, email, dan password diperlukan"}), 400

    session = Session()
    try:
        # Cek jika username atau email sudah ada
        existing_user = session.query(User).filter_by(username=username).first()
        if existing_user:
            return jsonify({"error": "Username sudah terdaftar"}), 409 # Conflict
        
        existing_user_email = session.query(User).filter_by(email=email).first()
        if existing_user_email:
            return jsonify({"error": "Email sudah terdaftar"}), 409 # Conflict

        new_user = User(
            username=username,
            password_hash=password, # Dalam produksi, ini harus di-hash (bcrypt/scrypt)
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
    data = request.json
    username = data.get('username')
    password = data.get('password') # Password mentah

    if not username or not password:
        return jsonify({"error": "Username dan password diperlukan"}), 400

    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user or user.password_hash != password: # Dalam produksi, bandingkan hash
            return jsonify({"error": "Username atau password salah"}), 401 # Unauthorized
        
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
    try:
        # PENTING: Gunakan text() dari sqlalchemy.sql untuk server_default
        from sqlalchemy.sql import text as sa_text 
        print("INFO: Attempting to create database tables (users table)...")
        Base.metadata.create_all(engine)
        print("INFO: Database tables created successfully or already exist.")
    except Exception as e:
        print(f"ERROR: Failed to create database tables at startup: {e}")
        # Jangan raise error di sini agar aplikasi Flask bisa start
        # dan kita bisa melihat errornya di browser/log jika database bermasalah.
        # Jika raise, Flask akan crash saat startup.
        pass 

    # Ambil PORT dari environment yang disediakan Railway, default ke 5000
    port = int(os.getenv("PORT", 5000))
    print(f"INFO: Flask app running on port {port}")
    app.run(debug=True, host='0.0.0.0', port=port)
