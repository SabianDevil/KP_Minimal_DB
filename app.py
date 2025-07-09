from flask import Flask, request, jsonify, render_template, g, send_from_directory
from datetime import datetime, timedelta
import re
import pytz
import sqlite3
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# --- Konfigurasi Flask dan Database ---
# Mendapatkan direktori kerja saat ini di dalam kontainer Docker
current_dir = os.getcwd()
app = Flask(__name__,
            template_folder=current_dir,  # Flask akan mencari index.html di direktori ini
            static_folder=current_dir)    # Flask akan mencari style.css & script.js di direktori ini

DATABASE = 'reminders.db'

# --- Fungsi Pembantu untuk Interaksi Database ---
def get_db():
    """Mendapatkan koneksi database SQLite. Membuat baru jika belum ada."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row # Mengembalikan baris sebagai objek mirip dict
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Menutup koneksi database saat konteks aplikasi selesai."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    """Menjalankan query SELECT ke database."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def insert_db(query, args=()):
    """Menjalankan query INSERT ke database."""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    lastrowid = cur.lastrowid
    cur.close()
    return lastrowid

def update_db(query, args=()):
    """Menjalankan query UPDATE atau DELETE ke database."""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    cur.close()

# --- Logika AI Pengingat Anda (diadaptasi untuk Web) ---
TIMEZONE_MAP = {
    "wib": "Asia/Jakarta", "wita": "Asia/Makassar", "wit": "Asia/Jayapura",
    "est": "America/New_York", "pst": "America/Los_Angeles", "gmt": "Etc/GMT",
    "utc": "Etc/UTC", "gmt+7": "Etc/GMT-7", "gmt-7": "Etc/GMT+7"
}
# Atur zona waktu lokal server, default ke Asia/Jakarta (WIB) jika tidak ada ENV TZ
LOCAL_TIMEZONE = pytz.timezone(os.environ.get('TZ', 'Asia/Jakarta'))

def add_months(sourcedate, months):
    """Menambahkan bulan ke objek datetime, menangani akhir bulan dengan benar."""
    month = sourcedate.month + months
    year = sourcedate.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(sourcedate.day, (datetime(year, month + 1, 1).date() - timedelta(days=1)).day if month < 12 else 31)
    return sourcedate.replace(year=year, month=month, day=day, tzinfo=sourcedate.tzinfo)

def extract_schedule(text):
    """Menguraikan teks input untuk mengekstrak informasi jadwal."""
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


    # Ekstraksi Deskripsi Event
    stopwords = ['ingatkan', 'saya', 'untuk', 'pada', 'di', 'tanggal', 'pukul', 'jam', 'paling lambat', 'mengingatkan', 'setelah', 'depan', 'setiap', 'tiap', 'ke depan', 'menit', 'lagi', 'dalam', 'kedepan']
    words = processed_text.split()
    final_event_description = ' '.join([word for word in words if word.lower() not in stopwords])
    final_event_description = final_event_description.replace("  ", " ").strip()

    if not final_event_description:
        final_event_description = "Pengingat"


    # Validasi Akhir dan Konversi Zona Waktu
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
    tz_name_full = dt_object.tzname()
    if tz_name_full:
        if "Western Indonesia Standard Time" in tz_name_full:
            return "WIB"
        elif "Central Indonesia Standard Time" in tz_name_full:
            return "WITA"
        elif "Eastern Indonesia Standard Time" in tz_name_full:
            return "WIT"
        # Untuk zona waktu lain, bisa return offset atau nama singkat jika ada
        return "" # Default, hilangkan jika bukan salah satu di atas
    return ""

# --- API Endpoints ---

# Rute untuk menyajikan halaman HTML utama
@app.route('/')
def serve_index():
    return render_template('index.html')

# Rute untuk menyajikan file CSS dari root
@app.route('/style.css')
def serve_css():
    return send_from_directory(current_dir, 'style.css')

# Rute untuk menyajikan file JavaScript dari root
@app.route('/script.js')
def serve_js():
    return send_from_directory(current_dir, 'script.js')

# API untuk menambahkan pengingat
@app.route('/add_reminder', methods=['POST'])
def add_reminder_api():
    note = request.json.get('note')
    if not note:
        return jsonify({"success": False, "message": "Catatan pengingat tidak boleh kosong."}), 400

    extracted_info = extract_schedule(note)

    if extracted_info:
        event = extracted_info['event']
        scheduled_time = extracted_info['datetime']
        repeat_type = extracted_info['repeat_type']
        repeat_interval = extracted_info['repeat_interval']

        # Simpan ke database
        insert_db('INSERT INTO reminders (event, datetime, repeat_type, repeat_interval, notified) VALUES (?, ?, ?, ?, ?)',
                  (event, scheduled_time.isoformat(), repeat_type, repeat_interval, 0))

        formatted_time_str = scheduled_time.strftime(f'%d %B %Y %H:%M {format_timezone_display(scheduled_time)}')
        return jsonify({"success": True, "message": f"Pengingat '{event}' pada {formatted_time_str} berhasil ditambahkan."}), 200
    else:
        return jsonify({"success": False, "message": "Tidak dapat mendeteksi jadwal dari catatan Anda. Coba format lain."}), 400

# API untuk mendapatkan semua pengingat
@app.route('/get_reminders', methods=['GET'])
def get_reminders_api():
    reminders = query_db('SELECT * FROM reminders ORDER BY datetime ASC')
    # Konversi Row objek ke dict dan datetime string ke objek datetime untuk frontend
    reminders_list = []
    for r in reminders:
        r_dict = dict(r)
        dt_obj = datetime.fromisoformat(r_dict['datetime']) # Konversi string ISO ke datetime object
        r_dict['datetime'] = dt_obj.isoformat() # Pastikan tetap string ISO untuk JSON
        r_dict['formatted_datetime'] = dt_obj.strftime(f'%d %B %Y %H:%M {format_timezone_display(dt_obj)}')
        r_dict['notified_status'] = "Selesai" if r_dict['notified'] else "Akan Datang"
        reminders_list.append(r_dict)
    
    return jsonify(reminders_list), 200

# API untuk mendapatkan pengingat untuk bulan tertentu (digunakan oleh kalender)
@app.route('/get_reminders_for_month', methods=['GET'])
def get_reminders_for_month():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if not year or not month:
        return jsonify({"error": "Missing year or month parameter"}), 400

    # Hitung rentang tanggal untuk bulan tersebut
    start_date = datetime(year, month, 1, 0, 0, 0, tzinfo=LOCAL_TIMEZONE)
    # Tanggal akhir bulan, termasuk hari terakhir
    if month == 12:
        end_date = datetime(year + 1, 1, 1, 23, 59, 59, tzinfo=LOCAL_TIMEZONE) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1, 23, 59, 59, tzinfo=LOCAL_TIMEZONE) - timedelta(days=1)
    
    reminders = query_db(
        'SELECT id, event, datetime FROM reminders WHERE datetime BETWEEN ? AND ? ORDER BY datetime ASC',
        (start_date.isoformat(), end_date.isoformat()) # Gunakan ISO format untuk query range
    )
    
    reminders_data = []
    for r in reminders:
        r_dict = dict(r)
        dt_obj = datetime.fromisoformat(r_dict['datetime'])
        reminders_data.append({
            'id': r_dict['id'],
            'event': r_dict['event'],
            'date': dt_obj.strftime('%Y-%m-%d') # Hanya tanggal untuk penandaan di kalender
        })
    
    return jsonify(reminders_data), 200

# API untuk menghapus pengingat
@app.route('/delete_reminder/<int:reminder_id>', methods=['DELETE'])
def delete_reminder_api(reminder_id):
    # Dapatkan pengingat untuk memastikan ada sebelum menghapus
    reminder_exists = query_db('SELECT id FROM reminders WHERE id = ?', (reminder_id,), one=True)
    if reminder_exists:
        update_db('DELETE FROM reminders WHERE id = ?', (reminder_id,))
        return jsonify({"success": True, "message": "Pengingat berhasil dihapus."}), 200
    else:
        return jsonify({"success": False, "message": "Pengingat tidak ditemukan."}), 404


# --- Scheduler untuk Mengecek Pengingat Jatuh Tempo ---
def check_reminders_job():
    """Tugas latar belakang untuk memeriksa dan memproses pengingat yang jatuh tempo."""
    with app.app_context(): # Pastikan scheduler berjalan dalam konteks aplikasi Flask
        now_local = datetime.now(LOCAL_TIMEZONE)
        
        # Ambil pengingat yang belum dinotifikasi
        reminders = query_db('SELECT * FROM reminders WHERE notified = 0 ORDER BY datetime ASC')

        for reminder_data in reminders:
            # Konversi string datetime dari DB ke objek datetime aware
            reminder_dt = datetime.fromisoformat(reminder_data['datetime'])
            
            # Pastikan kedua datetime memiliki tzinfo untuk perbandingan yang benar
            if reminder_dt.tzinfo is None and now_local.tzinfo is not None:
                reminder_dt = LOCAL_TIMEZONE.localize(reminder_dt.replace(tzinfo=None))
            elif reminder_dt.tzinfo is not None and now_local.tzinfo is None:
                now_local = LOCAL_TIMEZONE.localize(now_local.replace(tzinfo=None)) # Make now_local aware
            
            # Periksa apakah pengingat sudah jatuh tempo
            if now_local >= reminder_dt:
                print(f"Mengirim notifikasi (simulasi di log) untuk: {reminder_data['event']} pada {reminder_dt}")
                
                # Jika pengingat tidak berulang, tandai sebagai dinotifikasi
                if reminder_data['repeat_type'] == 'none':
                    update_db('UPDATE reminders SET notified = 1 WHERE id = ?', (reminder_data['id'],))
                else:
                    # Untuk pengingat berulang, hitung waktu berikutnya dan reset notified
                    next_datetime = reminder_dt
                    repeat_interval = reminder_data['repeat_interval']

                    if reminder_data['repeat_type'] == 'yearly':
                        next_datetime = next_datetime.replace(year=next_datetime.year + repeat_interval, tzinfo=next_datetime.tzinfo)
                    elif reminder_data['repeat_type'] == 'monthly_interval':
                        next_datetime = add_months(next_datetime, repeat_interval)
                    
                    # Maju cepat jika pengingat terlewat banyak kali (misal server mati lama)
                    while next_datetime <= now_local:
                        if reminder_data['repeat_type'] == 'yearly':
                            next_datetime = next_datetime.replace(year=next_datetime.year + repeat_interval, tzinfo=next_datetime.tzinfo)
                        elif reminder_data['repeat_type'] == 'monthly_interval':
                            next_datetime = add_months(next_datetime, repeat_interval)
                    
                    update_db('UPDATE reminders SET datetime = ?, notified = 0 WHERE id = ?', 
                              (next_datetime.isoformat(), reminder_data['id']))
        get_db().commit() # Commit perubahan setelah semua update selesai

scheduler = BackgroundScheduler()
# Jadwalkan check_reminders_job untuk berjalan setiap 30 detik
scheduler.add_job(check_reminders_job, IntervalTrigger(seconds=30), id='check_reminders', replace_existing=True)

# Mulai scheduler hanya jika aplikasi tidak dijalankan langsung (misal oleh Gunicorn)
# Ini mencegah scheduler berjalan ganda jika ada multiple Gunicorn workers
if __name__ != '__main__':
    scheduler.start()
    print("Scheduler started in background for production.")

# --- Main Run Block ---
if __name__ == '__main__':
    # Pastikan database terinisialisasi saat pengembangan lokal
    if not os.path.exists(DATABASE):
        from database import init_db
        init_db()
    
    # Jalankan scheduler di main thread saat pengembangan lokal
    scheduler.start()
    print("Scheduler started for local development.")
    
    # Dapatkan port dari variabel lingkungan (dari Railway) atau default ke 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
