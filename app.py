import os
from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
import re
import pytz 
import uuid # Diperlukan untuk ID sementara jika tidak pakai DB


# --- INISIALISASI APLIKASI FLASK ---
app = Flask(__name__)

# --- PENYIMPANAN PENGINGAT DI MEMORI (TIDAK PERSISTEN) ---
# Ini akan menyimpan pengingat hanya selama aplikasi berjalan.
# Data akan hilang saat aplikasi di-restart (misalnya saat deployment baru).
reminders_in_memory = []

# --- KONFIGURASI ZONA WAKTU ---
LOCAL_TIMEZONE = pytz.timezone('Asia/Jakarta') 

TIMEZONE_MAP = {
    "wib": "Asia/Jakarta",
    "wita": "Asia/Makassar",
    "wit": "Asia/Jayapura",
    "est": "America/New_York",
    "pst": "America/Los_Angeles",
    "gmt": "Etc/GMT",
    "utc": "Etc/UTC",
    "gmt+7": "Etc/GMT-7",
    "gmt-7": "Etc/GMT+7"
}

# --- MODEL PENGINGAT (VERSI SIMPLIFIKASI UNTUK MEMORI) ---
# Tidak ada lagi interaksi SQLAlchemy atau kolom database
class Reminder:
    def __init__(self, id, user_id, text, reminder_time, created_at, is_completed, repeat_type, repeat_interval):
        self.id = id
        self.user_id = user_id
        self.text = text
        self.reminder_time = reminder_time # datetime object
        self.created_at = created_at
        self.is_completed = is_completed
        self.repeat_type = repeat_type
        self.repeat_interval = repeat_interval

    def to_dict(self):
        # Pastikan semua nilai dikonversi dengan aman ke string/tipe dasar JSON
        reminder_time_iso = None
        if self.reminder_time:
            try:
                reminder_time_iso = self.reminder_time.isoformat()
            except Exception as dt_e:
                print(f"ERROR in to_dict (reminder_time): Failed to isoformat {self.reminder_time}: {dt_e}")
                reminder_time_iso = self.reminder_time.strftime('%Y-%m-%dT%H:%M:%S')

        created_at_iso = None
        if self.created_at:
            try:
                created_at_iso = self.created_at.isoformat()
            except Exception as dt_e:
                print(f"ERROR in to_dict (created_at): Failed to isoformat {self.created_at}: {dt_e}")
                created_at_iso = self.created_at.strftime('%Y-%m-%dT%H:%M:%S')

        return {
            "id": str(self.id) if self.id else None, 
            "user_id": str(self.user_id) if self.user_id else "", 
            "text": str(self.text) if self.text else "N/A", 
            "reminder_time": reminder_time_iso,
            "created_at": created_at_iso,
            "is_completed": bool(self.is_completed), 
            "repeat_type": str(self.repeat_type) if self.repeat_type else "none", 
            "repeat_interval": int(self.repeat_interval) if self.repeat_interval is not None else 0 
        }


# --- FUNGSI NLP: extract_schedule ---
# Kode ini tetap sama
def extract_schedule(text):
    original_text = text.lower()
    processed_text = original_text 
    
    now_local = datetime.now(LOCAL_TIMEZONE) 
    scheduled_datetime_aware = now_local 
    
    target_tz = LOCAL_TIMEZONE 
    tz_matched = False
    tz_pattern_parts = [re.escape(k) for k in TIMEZONE_MAP.keys()]
    tz_pattern = r'\b(' + '|'.join(tz_pattern_parts) + r')\b'
    
    tz_match = re.search(tz_pattern, processed_text, re.IGNORECASE)
    if tz_match:
        tz_abbr = tz_match.group(1).lower()
        try:
            target_tz = pytz.timezone(TIMEZONE_MAP[tz_abbr])
            processed_text = processed_text.replace(tz_match.group(0), '').strip() 
            tz_matched = True
        except pytz.UnknownTimeZoneError:
            pass 
    
    repeat_type = "none"
    repeat_interval = 0
    default_hour, default_minute = 9, 0

    monthly_repeat_pattern = r'(?:setiap|tiap)\s*(\d+)\s*bulan|(?:(\d+)\s*bulan\s*kedepan)'
    monthly_repeat_match = re.search(monthly_repeat_pattern, processed_text)
    if monthly_repeat_match:
        repeat_type = "monthly_interval"
        if monthly_repeat_match.group(1):
            repeat_interval = int(monthly_repeat_match.group(1))
        elif monthly_repeat_match.group(2):
            repeat_interval = int(monthly_repeat_match.group(2))
        processed_text = re.sub(monthly_repeat_pattern, '', processed_text).strip()

    yearly_repeat_pattern_explicit = r'(?:setiap|tiap)\s*(\d+)\s*tahun|(?:(\d+)\s*tahun\s*kedepan)'
    yearly_repeat_match_explicit = re.search(yearly_repeat_pattern_explicit, processed_text)
    if yearly_repeat_match_explicit:
        repeat_type = "yearly"
        if yearly_repeat_match_explicit.group(1):
            repeat_interval = int(yearly_repeat_match_explicit.group(1))
        elif yearly_repeat_match_explicit.group(2):
            repeat_interval = int(yearly_repeat_match_explicit.group(2))
        processed_text = re.sub(yearly_repeat_pattern_explicit, '', processed_text).strip()
    elif "setiap tahun" in processed_text or "tiap tahun" in processed_text:
        repeat_type = "yearly"
        repeat_interval = 1 
        processed_text = processed_text.replace("setiap tahun", "").replace("tiap tahun", "").strip()
    
    if repeat_type == "monthly_interval" and ("tahun" in original_text or "yearly" in original_text):
        monthly_repeat_match = None
        repeat_type = "none"
        repeat_interval = 0

    found_explicit_date = False

    date_keywords_map = {
        "hari ini": now_local.date(),
        "besok": (now_local + timedelta(days=1)).date(),
        "lusa": (now_local + timedelta(days=2)).date(),
        "minggu depan": (now_local + timedelta(weeks=1)).date(),
        "bulan depan": (now_local.replace(day=1) + timedelta(days=32)).replace(day=now_local.day).date()
    }
    
    for keyword, date_obj in date_keywords_map.items():
        if keyword in processed_text:
            scheduled_datetime_aware = scheduled_datetime_aware.replace(year=date_obj.year, month=date_obj.month, day=date_obj.day, tzinfo=scheduled_datetime_aware.tzinfo)
            processed_text = processed_text.replace(keyword, '').strip()
            found_explicit_date = True
            break
    
    day_of_week_map = {
        "senin": 0, "selasa": 1, "rabu": 2, "kamis": 3, "jumat": 4, "sabtu": 5, "minggu": 6
    }
    if not found_explicit_date:
        for day_name, day_num in day_of_week_map.items():
            if f"minggu depan {day_name}" in processed_text or f"depan {day_name}" in processed_text:
                days_ahead = (day_num - now_local.weekday() + 7) % 7 + 7
                if days_ahead == 0: days_ahead = 7
                target_date = now_local.date() + timedelta(days=days_ahead)
                scheduled_datetime_aware = scheduled_datetime_aware.replace(year=target_date.year, month=target_date.month, day=target_date.day, tzinfo=scheduled_datetime_aware.tzinfo)
                processed_text = processed_text.replace(f"minggu depan {day_name}", "").replace(f"depan {day_name}", "").strip()
                found_explicit_date = True
                break
            elif day_name in processed_text:
                days_ahead = (day_num - now_local.weekday() + 7) % 7
                if days_ahead == 0: days_ahead = 7
                target_date = now_local.date() + timedelta(days=days_ahead)
                scheduled_datetime_aware = scheduled_datetime_aware.replace(year=target_date.year, month=target_date.month, day=target_date.day, tzinfo=scheduled_datetime_aware.tzinfo)
                processed_text = processed_text.replace(day_name, "").strip()
                found_explicit_date = True
                
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
                    scheduled_datetime_aware = scheduled_datetime_aware.replace(year=parsed_date.year, month=parsed_date.month, day=parsed_date.day, tzinfo=scheduled_datetime_aware.tzinfo)
                    processed_text = re.sub(date_pattern, '', processed_text, flags=re.IGNORECASE).strip()
                    found_explicit_date = True
            except (ValueError, TypeError):
                pass
    
    found_time_set_by_match = False

    relative_time_pattern = r'\b(dalam\s+)?(\d+)\s*(jam|menit)\s*(lagi|ke\s+depan)?\b'
    relative_time_match = re.search(relative_time_pattern, processed_text, re.IGNORECASE)
    if relative_time_match:
        value = int(relative_time_match.group(2))
        unit = relative_time_match.group(3)
        
        if unit == "jam":
            scheduled_datetime_aware = now_local + timedelta(hours=value)
        elif unit == "menit":
            scheduled_datetime_aware = now_local + timedelta(minutes=value)
        
        found_time_set_by_match = True
        processed_text = re.sub(relative_time_pattern, '', processed_text, flags=re.IGNORECASE).strip()
    
    waktu_sholat_map = {
        "subuh": "05:00",
        "dzuhur": "12:00",
        "ashar": "15:00",
        "maghrib": "18:00",
        "isya": "19:30"
    }
    
    if not found_time_set_by_match:
        for sholat_name, sholat_time_str in waktu_sholat_map.items():
            if f"setelah {sholat_name}" in processed_text or sholat_name in processed_text:
                try:
                    hour, minute = map(int, sholat_time_str.split(':'))
                    temp_time = scheduled_datetime_aware.replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=scheduled_datetime_aware.tzinfo)
                    if f"setelah {sholat_name}" in processed_text:
                        temp_time += timedelta(minutes=30)
                    
                    if temp_time < now_local and temp_time.date() == scheduled_datetime_aware.date():
                        temp_time += timedelta(days=1)

                    scheduled_datetime_aware = temp_time
                    found_time_set_by_match = True
                    processed_text = processed_text.replace(f"setelah {sholat_name}", "").replace(sholat_name, "").strip()
                    break
                except ValueError:
                    pass

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
                
                temp_time = scheduled_datetime_aware.replace(hour=hour_extracted, minute=minute_extracted, second=0, microsecond=0, tzinfo=scheduled_datetime_aware.tzinfo)
                
                if temp_time < now_local and temp_time.date() == scheduled_datetime_aware.date():
                    temp_time += timedelta(days=1)

                scheduled_datetime_aware = temp_time
                found_time_set_by_match = True
                
                processed_text = re.sub(time_pattern, '', processed_text, flags=re.IGNORECASE).strip()
            except (ValueError, TypeError):
                pass

    if not found_time_set_by_match:
        temp_time = scheduled_datetime_aware.replace(hour=default_hour, minute=default_minute, second=0, microsecond=0, tzinfo=scheduled_datetime_aware.tzinfo)
        if temp_time < now_local and temp_time.date() == scheduled_datetime_aware.date():
            temp_time += timedelta(days=1)
        scheduled_datetime_aware = temp_time


    event_description = processed_text 
    stopwords = ['ingatkan', 'saya', 'untuk', 'pada', 'di', 'tanggal', 'pukul', 'jam', 'paling lambat', 'mengingatkan', 'setelah', 'depan', 'setiap', 'tiap', 'ke depan', 'menit', 'lagi', 'dalam', 'kedepan']
    words = event_description.split()
    final_event_description = ' '.join([word for word in words if word.lower() not in stopwords])
    final_event_description = final_event_description.replace("  ", " ").strip()

    if not final_event_description:
        final_event_description = "Pengingat"


    tolerance = timedelta(seconds=2)
    
    if tz_matched: 
        scheduled_datetime_naive_temp = scheduled_datetime_aware.replace(tzinfo=None)
        scheduled_datetime_localized_target = target_tz.localize(scheduled_datetime_naive_temp)
        scheduled_datetime_final = scheduled_datetime_localized_target.astimezone(LOCAL_TIMEZONE)
    else:
        scheduled_datetime_final = scheduled_datetime_aware 

    if scheduled_datetime_final < now_local - tolerance:
        return None
    
    if scheduled_datetime_final:
        return {"event": final_event_description, "datetime": scheduled_datetime_final, "repeat_type": repeat_type, "repeat_interval": repeat_interval}
    return None

def format_timezone_display(dt_object):
    """Membantu memformat tampilan zona waktu agar lebih ringkas."""
    if dt_object is None:
        return ""
    tz_name_full = dt_object.tzname()
    if tz_name_full:
        if "Western Indonesia Standard Time" in tz_name_full:
            return "WIB"
        elif "Central Indonesia Standard Time" in tz_name_full:
            return "WITA"
        elif "Eastern Indonesia Standard Time" in tz_name_full:
            return "WIT"
        return tz_name_full
    return "" 

# --- Routes Aplikasi Web Anda ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Route terkait Login/Register dihapus ---

@app.route('/set_reminder', methods=['POST'])
def set_reminder():
    session = Session()
    try:
        data = request.json
        reminder_text = data.get('text')
        user_id = "default_user" # Default user_id karena tidak ada login/register

        if not reminder_text:
            return jsonify({"error": "Teks pengingat diperlukan"}), 400

        parsed_schedule = extract_schedule(reminder_text)

        if not parsed_schedule:
            return jsonify({"error": "Tidak dapat memahami jadwal pengingat dari teks yang diberikan."}), 400

        new_reminder = Reminder(
            user_id=user_id,
            text=parsed_schedule['event'],
            reminder_time=parsed_schedule['datetime'].replace(tzinfo=None), # Simpan naive datetime untuk SQLite
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
        reminders = session.query(Reminder).filter_by(user_id="default_user", is_completed=False).order_by(Reminder.reminder_time).all()
        return jsonify([r.to_dict() for r in reminders]), 200
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
        from sqlalchemy.sql import text as sa_text 
        print("INFO: Attempting to create database tables (reminders table)...")
        Base.metadata.create_all(engine) 
        print("INFO: Database tables created or already exists.")
    except Exception as e:
        print(f"ERROR: Failed to create database tables at startup: {e}")
        pass 

    port = int(os.getenv("PORT", 5000))
    print(f"INFO: Flask app running on port {port}")
    app.run(debug=True, host='0.0.0.0', port=port)
