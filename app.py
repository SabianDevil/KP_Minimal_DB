import os
from flask import Flask, request, jsonify, render_template
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Integer
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, timedelta # pytz dihilangkan
import re

# --- INISIALISASI APLIKASI FLASK ---
app = Flask(__name__)

# --- KONFIGURASI DATABASE SQLite ---
DATABASE_URL = "sqlite:///app_database.db" 

print(f"DEBUG: Menggunakan DATABASE_URL: '{DATABASE_URL}'") 

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as connection:
        print("INFO: Database connection engine created and tested successfully with SQLite.")
except Exception as e:
    print(f"FATAL ERROR: Failed to create database engine or connect: {e}")
    raise e 

Session = sessionmaker(bind=engine)
Base = declarative_base()

# --- MODEL DATABASE (Hanya Reminder, disederhanakan) ---
class Reminder(Base):
    __tablename__ = 'reminders'
    id = Column(Integer, primary_key=True, autoincrement=True) 
    user_id = Column(String, default="default_user", nullable=False) 
    text = Column(String, nullable=False)
    reminder_time = Column(DateTime, nullable=False) # Tanpa timezone=True
    created_at = Column(DateTime, default=datetime.utcnow) 
    is_completed = Column(Boolean, default=False)
    # repeat_type dan repeat_interval dihilangkan dari model
    # karena tidak diimplementasikan di versi dasar ini

    def __repr__(self):
        return f"<Reminder(id='{self.id}', text='{self.text}', time='{self.reminder_time}')>"

    def to_dict(self):
        # Konversi datetime ke string ISO tanpa info TZ
        reminder_time_iso = self.reminder_time.isoformat() if self.reminder_time else None
        created_at_iso = self.created_at.isoformat() if self.created_at else None

        return {
            "id": str(self.id) if self.id else None, 
            "user_id": str(self.user_id) if self.user_id else "", 
            "text": str(self.text) if self.text else "N/A", 
            "reminder_time": reminder_time_iso,
            "created_at": created_at_iso,
            "is_completed": bool(self.is_completed), 
            "repeat_type": "none", # Default karena fitur tidak aktif
            "repeat_interval": 0   # Default karena fitur tidak aktif
        }

# --- FUNGSI NLP: extract_schedule (disimplifikasi) ---
# Hanya menangani 'hari ini', 'besok', 'X jam/menit kedepan' dan jam numerik.
# Tanpa zona waktu atau waktu sholat kompleks.
def extract_schedule(text):
    original_text = text.lower()
    processed_text = original_text 
    
    now_local = datetime.now() # Tanpa pytz, ini akan menjadi naive datetime lokal
    scheduled_datetime_naive = now_local 
    
    # Repeat type & interval dihilangkan dari deteksi di sini
    repeat_type = "none"
    repeat_interval = 0

    # 1. Ekstraksi Tanggal Relatif
    date_keywords_map = {
        "hari ini": now_local.date(),
        "besok": (now_local + timedelta(days=1)).date(),
        "lusa": (now_local + timedelta(days=2)).date(),
    }
    
    found_explicit_date = False
    for keyword, date_obj in date_keywords_map.items():
        if keyword in processed_text:
            # Gunakan replace() tanpa tzinfo
            scheduled_datetime_naive = scheduled_datetime_naive.replace(year=date_obj.year, month=date_obj.month, day=date_obj.day)
            processed_text = processed_text.replace(keyword, '').strip()
            found_explicit_date = True
            break
        
    # Regex untuk tanggal spesifik (dd MonthPPPP atau dd/mm/YYYY)
    if not found_explicit_date:
        date_pattern = r'\b(\d{1,2}) (januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember) (\d{4})\b|\b(\d{1,2})/(\d{1,2})/(\d{4})\b'
        found_date_match = re.search(date_pattern, processed_text, re.IGNORECASE)
        if found_date_match:
            try:
                parsed_date = None
                if found_date_match.group(2):
                    day_str, month_name, year_str = found_date_match.group(1, 2, 3)
                    bulan_map = {
                        "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
                        "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12
                    }
                    month_num = bulan_map.get(month_name.lower())
                    if month_num:
                        parsed_date = datetime(int(year_str), month_num, int(day_str)).date()
                elif found_date_match.group(4):
                    day_str, month_str, year_str = found_date_match.group(4, 5, 6)
                    parsed_date = datetime(int(year_str), int(month_str), int(day_str)).date()

                if parsed_date:
                    scheduled_datetime_naive = scheduled_datetime_naive.replace(year=parsed_date.year, month=parsed_date.month, day=parsed_date.day)
                    processed_text = re.sub(date_pattern, '', processed_text, flags=re.IGNORECASE).strip()
                    found_explicit_date = True
            except (ValueError, TypeError):
                pass
    
    # 2. Ekstraksi Waktu Relatif/Numerik
    found_time_set_by_match = False

    relative_time_pattern = r'\b(dalam\s+)?(\d+)\s*(jam|menit)\s*(lagi|ke\s+depan)?\b'
    relative_time_match = re.search(relative_time_pattern, processed_text, re.IGNORECASE)
    if relative_time_match:
        value = int(relative_time_match.group(2))
        unit = relative_time_match.group(3)
        
        if unit == "jam":
            scheduled_datetime_naive = now_local + timedelta(hours=value)
        elif unit == "menit":
            scheduled_datetime_naive = now_local + timedelta(minutes=value)
        
        found_time_set_by_match = True
        processed_text = re.sub(relative_time_pattern, '', processed_text, flags=re.IGNORECASE).strip()
    
    if not found_time_set_by_match:
        time_pattern = r'\b(jam |pukul )?(\d{1,2}([\.:]\d{2})?)\s*(pagi|siang|sore|malam|am|pm)?\b'
        found_time_match = re.search(time_pattern, processed_text, re.IGNORECASE)

        if found_time_match:
            try:
                time_str_raw = found_time_match.group(2)
                ampm_str = (found_time_match.group(4) or '').lower()

                hour_extracted = 0
                minute_extracted = 0

                if ':' in time_str_raw:
                    hour_extracted, minute_extracted = map(int, time_str_raw.split(':'))
                elif '.' in time_str_raw:
                    hour_extracted, minute_extracted = map(int, time_str_raw.split('.'))
                else:
                    hour_extracted = int(time_str_raw)
                    
                if 'pagi' in ampm_str:
                    if hour_extracted == 12: hour_extracted = 0
                elif 'siang' in ampm_str:
                    if hour_extracted < 12: hour_extracted += 12
                elif 'sore' in ampm_str or 'pm' in ampm_str:
                    if hour_extracted < 12: hour_extracted += 12
                elif 'malam' in ampm_str:
                    if hour_extracted < 12: hour_extracted += 12
                    if hour_extracted == 24: hour_extracted = 0
                    
                if not (0 <= hour_extracted <= 23 and 0 <= minute_extracted <= 59):
                    raise ValueError("Invalid time")
                
                temp_time = scheduled_datetime_naive.replace(hour=hour_extracted, minute=minute_extracted, second=0, microsecond=0)
                
                if temp_time < now_local and temp_time.date() == scheduled_datetime_naive.date():
                    temp_time += timedelta(days=1)

                scheduled_datetime_naive = temp_time
                found_time_set_by_match = True
                
                processed_text = re.sub(time_pattern, '', processed_text, flags=re.IGNORECASE).strip()
            except (ValueError, TypeError):
                pass

    if not found_time_set_by_match: # Jika tidak ada waktu spesifik yang terdeteksi, gunakan default jam 9 pagi
        temp_time = scheduled_datetime_naive.replace(hour=default_hour, minute=default_minute, second=0, microsecond=0)
        if temp_time < now_local and temp_time.date() == scheduled_datetime_naive.date():
            temp_time += timedelta(days=1)
        scheduled_datetime_naive = temp_time


    # 3. Ekstraksi Deskripsi Event
    stopwords = ['ingatkan', 'saya', 'untuk', 'pada', 'di', 'tanggal', 'pukul', 'jam', 'paling lambat', 'mengingatkan', 'setelah', 'depan', 'setiap', 'tiap', 'ke depan', 'menit', 'lagi', 'dalam', 'kedepan', 'isya', 'subuh', 'dzuhur', 'ashar', 'maghrib', 'malam', 'sore', 'siang', 'pagi']
    words = processed_text.split()
    final_event_description = ' '.join([word for word in words if word.lower() not in stopwords])
    final_event_description = final_event_description.replace("  ", " ").strip()

    if not final_event_description:
        final_event_description = "Pengingat"


    # 4. Validasi Akhir dan Penyesuaian Waktu Lampau
    tolerance = timedelta(seconds=2)
    
    if scheduled_datetime_naive < now_local - tolerance:
        return None
    
    if scheduled_datetime_naive:
        return {"event": final_event_description, "datetime": scheduled_datetime_naive, "repeat_type": repeat_type, "repeat_interval": repeat_interval}
    return None

# --- Route (Endpoint) untuk Aplikasi Web Anda ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/set_reminder', methods=['POST'])
def set_reminder():
    session = Session()
    try:
        data = request.json
        reminder_text = data.get('text')
        user_id = "default_user" 

        if not reminder_text:
            return jsonify({"error": "Teks pengingat diperlukan"}), 400

        parsed_schedule = extract_schedule(reminder_text)

        if not parsed_schedule:
            return jsonify({"error": "Tidak dapat memahami jadwal pengingat dari teks yang diberikan."}), 400

        # Konversi datetime ke naive (sudah naive dari extract_schedule)
        # Jika datetime.utcnow() digunakan untuk created_at, kita bisa menyimpan naive datetime di DB
        new_reminder = Reminder(
            user_id=user_id,
            text=parsed_schedule['event'],
            reminder_time=parsed_schedule['datetime'], # Ini sudah naive
            repeat_type=parsed_schedule['repeat_type'],
            repeat_interval=parsed_schedule['repeat_interval']
        )
        session.add(new_reminder)
        session.commit()
        return jsonify({"message": "Pengingat berhasil diatur!", "reminder": new_reminder.to_dict()}), 201
    except Exception as e:
        session.rollback()
        print(f"FATAL ERROR in set_reminder: {e}")
        return jsonify({"error": f"Terjadi kesalahan server saat mengatur pengingat: {str(e)}"}), 500
    finally:
        session.close()

@app.route('/get_reminders', methods=['GET'])
def get_reminders():
    session = Session()
    try:
        reminders = session.query(Reminder).filter_by(user_id="default_user").order_by(Reminder.reminder_time).all()
        reminders_data = []
        for r in reminders:
            r_dict = r.to_dict() 
            # Pastikan reminder_time_display diformat dengan benar
            if r_dict['reminder_time']: 
                # Konversi string ISO ke datetime object
                dt_obj_from_iso = datetime.fromisoformat(r_dict['reminder_time']) 
                # Tidak ada format_timezone_display jika pytz tidak diimpor
                r_dict['reminder_time_display'] = dt_obj_from_iso.strftime('%d %B %Y %H:%M')
            else:
                r_dict['reminder_time_display'] = "Waktu tidak tersedia" 
            
            reminders_data.append(r_dict)

        return jsonify(reminders_data), 200
    except Exception as e:
        print(f"FATAL ERROR in get_reminders: {e}")
        return jsonify({"error": f"Terjadi kesalahan server saat mengambil pengingat: {str(e)}"}), 500
    finally:
        session.close()

@app.route('/complete_reminder/<int:reminder_id>', methods=['POST'])
def complete_reminder(reminder_id):
    session = Session()
    try:
        reminder = session.query(Reminder).filter_by(id=reminder_id).first()
        if not reminder:
            return jsonify({"error": "Pengingat tidak ditemukan"}), 404
        
        reminder.is_completed = True
        session.commit()
        return jsonify({"message": "Pengingat ditandai selesai!", "reminder": reminder.to_dict()}), 200
    except Exception as e:
        session.rollback()
        print(f"FATAL ERROR in complete_reminder: {e}")
        return jsonify({"error": f"Terjadi kesalahan server saat menyelesaikan pengingat: {str(e)}"}), 500
    finally:
        session.close()

@app.route('/delete_reminder/<int:reminder_id>', methods=['DELETE'])
def delete_reminder(reminder_id):
    session = Session()
    try:
        reminder = session.query(Reminder).filter_by(id=reminder_id).first()
        if not reminder:
            return jsonify({"error": "Pengingat tidak ditemukan"}), 404
        
        session.delete(reminder)
        session.commit()
        return jsonify({"message": "Pengingat berhasil dihapus!"}), 200
    except Exception as e:
        session.rollback()
        print(f"FATAL ERROR in delete_reminder: {e}")
        return jsonify({"error": f"Terjadi kesalahan server saat menghapus pengingat: {str(e)}"}), 500
    finally:
        session.close()

# --- Bagian untuk menjalankan Flask App ---
if __name__ == '__main__':
    try:
        # Untuk SQLite, tidak perlu server_default di sini
        # from sqlalchemy.sql import text as sa_text 
        print("INFO: Attempting to create database tables (reminders table)...")
        Base.metadata.create_all(engine) 
        print("INFO: Database tables created or already exists.")
    except Exception as e:
        print(f"ERROR: Failed to create database tables at startup: {e}")
        pass 

    port = int(os.getenv("PORT", 5000))
    print(f"INFO: Flask app running on port {port}")
    app.run(debug=True, host='0.0.0.0', port=port)
