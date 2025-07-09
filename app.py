import os
from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
import re

# --- INISIALISASI APLIKASI FLASK ---
app = Flask(__name__)

# --- PENYIMPANAN PENGINGAT DI MEMORI (TIDAK PERSISTEN) ---
# Ini akan menyimpan pengingat hanya selama aplikasi berjalan.
reminders_in_memory = []

# --- MODEL PENGINGAT (VERSI SIMPLIFIKASI UNTUK MEMORI) ---
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
        # Format datetime ke string ISO tanpa info TZ
        reminder_time_iso = self.reminder_time.isoformat() if self.reminder_time else None
        created_at_iso = self.created_at.isoformat() if self.created_at else None

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


# --- FUNGSI NLP: extract_schedule (SANGAT DASAR) ---
# Hanya menangani 'hari ini', 'besok', 'X jam/menit kedepan' dan jam numerik.
# Tanpa zona waktu, waktu sholat, atau pola pengulangan yang kompleks.
def extract_schedule(text):
    original_text = text.lower()
    processed_text = original_text 
    
    now_local = datetime.now() # Naive datetime, tanpa zona waktu
    scheduled_datetime_naive = now_local 
    
    repeat_type = "none" 
    repeat_interval = 0

    # 1. Ekstraksi Tanggal Relatif (Hari Ini, Besok, Lusa)
    date_keywords_map = {
        "hari ini": now_local.date(),
        "besok": (now_local + timedelta(days=1)).date(),
        "lusa": (now_local + timedelta(days=2)).date(),
    }
    
    found_explicit_date = False
    for keyword, date_obj in date_keywords_map.items():
        if keyword in processed_text:
            scheduled_datetime_naive = scheduled_datetime_naive.replace(year=date_obj.year, month=date_obj.month, day=date_obj.day)
            processed_text = processed_text.replace(keyword, '').strip()
            found_explicit_date = True
            break
        
    # Regex untuk tanggal spesifik (dd MonthYYYY atau dd/mm/YYYY)
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
    default_hour, default_minute = 9, 0 # Default jam 9 pagi jika tidak ada waktu

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

    if not found_time_set_by_match: # Jika tidak ada waktu spesifik, default ke jam 9 pagi besok
        temp_time = scheduled_datetime_naive.replace(hour=default_hour, minute=default_minute, second=0, microsecond=0)
        if temp_time < now_local and temp_time.date() == scheduled_datetime_naive.date():
            temp_time += timedelta(days=1)
        scheduled_datetime_naive = temp_time


    # 3. Ekstraksi Deskripsi Event
    # Stopwords dihilangkan untuk kesederhanaan
    stopwords = ['ingatkan', 'saya', 'untuk', 'pada', 'di', 'tanggal', 'pukul', 'jam', 'paling lambat', 'mengingatkan', 'setelah', 'depan', 'setiap', 'tiap', 'ke depan', 'menit', 'lagi', 'dalam', 'kedepan', 'isya', 'subuh', 'dzuhur', 'ashar', 'maghrib', 'malam', 'sore', 'siang', 'pagi', 'minggu', 'senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu', 'bulan', 'tahun']
    words = processed_text.split()
    final_event_description = ' '.join([word for word in words if word.lower() not in stopwords])
    final_event_description = final_event_description.replace("  ", " ").strip()

    if not final_event_description:
        final_event_description = "Pengingat"


    # 4. Validasi Akhir
    tolerance = timedelta(seconds=2)
    
    if scheduled_datetime_naive < now_local - tolerance:
        print(f"DEBUG: Waktu yang diekstrak ({scheduled_datetime_naive}) sudah lampau dari sekarang ({now_local}). Mengembalikan None.")
        return None 
    
    if scheduled_datetime_naive:
        return {"event": final_event_description, "datetime": scheduled_datetime_naive, "repeat_type": repeat_type, "repeat_interval": repeat_interval}
    return None

# --- Routes Aplikasi Minimalis ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/set_reminder', methods=['POST'])
def set_reminder_api():
    # Menggunakan list global di memori, bukan database atau ORM
    global reminders_in_memory
    
    data = request.json
    reminder_text = data.get('text')

    if not reminder_text:
        return jsonify({"error": "Teks pengingat diperlukan"}), 400

    parsed_schedule = extract_schedule(reminder_text)

    if not parsed_schedule:
        return jsonify({"error": "Tidak dapat memahami jadwal pengingat dari teks yang diberikan."}), 400

    # Membuat objek Reminder sederhana (bukan model SQLAlchemy)
    new_reminder_obj = Reminder(
        id=str(uuid.uuid4()), # ID unik sementara
        user_id="default_user",
        text=parsed_schedule['event'],
        reminder_time=parsed_schedule['datetime'], # Ini sudah naive
        created_at=datetime.now(), # created_at juga naive
        is_completed=False,
        repeat_type=parsed_schedule['repeat_type'],
        repeat_interval=parsed_schedule['repeat_interval']
    )
    
    reminders_in_memory.append(new_reminder_obj)
    # Urutkan berdasarkan waktu
    reminders_in_memory.sort(key=lambda r: r.reminder_time)

    print(f"DEBUG: Pengingat baru ditambahkan ke memori: {new_reminder_obj.to_dict()}")
    return jsonify({"message": "Pengingat berhasil diatur (disimpan di memori)!", "reminder": new_reminder_obj.to_dict()}), 201


@app.route('/get_reminders', methods=['GET'])
def get_reminders_api():
    # Menggunakan list global di memori, bukan database
    global reminders_in_memory
    
    print("DEBUG: Memulai get_reminders_api (dari memori).")
    
    reminders_data = []
    # Loop melalui objek Reminder di memori dan ubah ke dict
    for r_obj in reminders_in_memory:
        try:
            r_dict = r_obj.to_dict() 
            
            # Format reminder_time_display
            if r_dict['reminder_time']: 
                # datetime.fromisoformat() akan bekerja dengan naive ISO string
                dt_obj_from_iso = datetime.fromisoformat(r_dict['reminder_time']) 
                r_dict['reminder_time_display'] = dt_obj_from_iso.strftime('%d %B %Y %H:%M')
            else:
                r_dict['reminder_time_display'] = "Waktu tidak tersedia" 
            
            reminders_data.append(r_dict)
        except Exception as e:
            print(f"FATAL ERROR: Gagal memproses atau menserialisasi pengingat dari memori: {e}")
            # Jika ada yang rusak, kita tetap mencoba mengirim yang lain, tapi log errornya
            pass # Jangan return 500 karena satu item rusak, biarkan yang lain terkirim

    print(f"DEBUG: Mengembalikan {len(reminders_data)} pengingat dari memori.")
    return jsonify(reminders_data), 200

@app.route('/complete_reminder/<string:reminder_id>', methods=['POST'])
def complete_reminder_api(reminder_id):
    global reminders_in_memory
    for r_obj in reminders_in_memory:
        if str(r_obj.id) == reminder_id:
            r_obj.is_completed = True
            print(f"DEBUG: Pengingat ID {reminder_id} ditandai selesai di memori.")
            return jsonify({"message": "Pengingat ditandai selesai (di memori)!", "reminder": r_obj.to_dict()}), 200
    return jsonify({"error": "Pengingat tidak ditemukan di memori"}), 404

@app.route('/delete_reminder/<string:reminder_id>', methods=['DELETE'])
def delete_reminder_api(reminder_id):
    global reminders_in_memory
    initial_len = len(reminders_in_memory)
    reminders_in_memory = [r_obj for r_obj in reminders_in_memory if str(r_obj.id) != reminder_id]
    if len(reminders_in_memory) < initial_len:
        print(f"DEBUG: Pengingat ID {reminder_id} dihapus dari memori.")
        return jsonify({"message": "Pengingat berhasil dihapus (dari memori)!"}), 200
    return jsonify({"error": "Pengingat tidak ditemukan di memori"}), 404


# --- Bagian untuk menjalankan Flask App ---
if __name__ == '__main__':
    # Flask di Railway/PythonAnywhere akan di-run oleh WSGI server (Gunicorn/uWSGI)
    # Jadi app.run() di sini hanya akan dieksekusi jika dijalankan secara lokal
    # Kita bisa hapus ini untuk deployment, tapi untuk local testing tidak masalah.
    port = int(os.getenv("PORT", 5000))
    print(f"INFO: Flask app running on port {port}")
    app.run(debug=True, host='0.0.0.0', port=port)
