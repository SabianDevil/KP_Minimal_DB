from flask import Flask, request, jsonify, render_template, g, send_from_directory
from datetime import datetime, timedelta
import re
import pytz
import sqlite3
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import json

# --- Import SpaCy ---
import spacy

# --- Konfigurasi Flask dan Database ---
current_dir = os.getcwd()
app = Flask(__name__,
            template_folder=current_dir,
            static_folder=current_dir)

DATABASE = 'reminders.db'

# --- Inisialisasi SpaCy di luar fungsi request untuk efisiensi ---
# Coba muat model bahasa Indonesia, fallback ke Inggris jika tidak ada
try:
    nlp = spacy.load("id_core_news_sm")
    print("SpaCy model 'id_core_news_sm' loaded successfully.")
except OSError:
    print("SpaCy model 'id_core_news_sm' not found, trying 'en_core_web_sm'.")
    try:
        nlp = spacy.load("en_core_web_sm")
        print("SpaCy model 'en_core_web_sm' loaded successfully.")
    except OSError:
        print("No SpaCy model found. Text parsing might be less accurate.")
        nlp = None # Atur nlp ke None jika tidak ada model yang dimuat


# --- Fungsi Pembantu untuk Interaksi Database ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def insert_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    lastrowid = cur.lastrowid
    cur.close()
    return lastrowid

def update_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    cur.close()

# --- Logika AI Pengingat Anda (Diadaptasi dengan SpaCy) ---
TIMEZONE_MAP = {
    "wib": "Asia/Jakarta", "wita": "Asia/Makassar", "wit": "Asia/Jayapura",
    "est": "America/New_York", "pst": "America/Los_Angeles", "gmt": "Etc/GMT",
    "utc": "Etc/UTC", "gmt+7": "Etc/GMT-7", "gmt-7": "Etc/GMT+7"
}
LOCAL_TIMEZONE = pytz.timezone(os.environ.get('TZ', 'Asia/Jakarta'))

def add_months(sourcedate, months):
    month = sourcedate.month + months
    year = sourcedate.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(sourcedate.day, (datetime(year, month + 1, 1).date() - timedelta(days=1)).day if month < 12 else 31)
    return sourcedate.replace(year=year, month=month, day=day, tzinfo=sourcedate.tzinfo)

def format_timezone_display(dt_object):
    tz_name_full = dt_object.tzname()
    if tz_name_full:
        if "Western Indonesia Standard Time" in tz_name_full:
            return "WIB"
        elif "Central Indonesia Standard Time" in tz_name_full:
            return "WITA"
        elif "Eastern Indonesia Standard Time" in tz_name_full:
            return "WIT"
        return ""
    return ""

def parse_single_schedule_fragment(text_fragment, now_local):
    """
    Mencoba menguraikan satu pengingat dari fragmen teks menggunakan SpaCy dan regex.
    """
    original_text_lower = text_fragment.lower()
    processed_text = text_fragment # Pertahankan casing asli untuk ekstraksi metadata jika perlu
    
    scheduled_datetime_aware = now_local
    target_tz = LOCAL_TIMEZONE
    tz_matched = False
    
    # --- 1. Ekstraksi Zona Waktu (tetap pakai regex untuk presisi) ---
    tz_pattern_parts = [re.escape(k) for k in TIMEZONE_MAP.keys()]
    tz_pattern = r'\b(' + '|'.join(tz_pattern_parts) + r')\b'
    tz_match = re.search(tz_pattern, original_text_lower, re.IGNORECASE)
    if tz_match:
        tz_abbr = tz_match.group(1).lower()
        try:
            target_tz = pytz.timezone(TIMEZONE_MAP[tz_abbr])
            processed_text = re.sub(tz_pattern, '', processed_text, flags=re.IGNORECASE).strip()
            tz_matched = True
        except pytz.UnknownTimeZoneError:
            pass

    # --- 2. Ekstraksi Tanggal dan Waktu menggunakan SpaCy (Prioritas Tinggi) ---
    spacy_date = None
    spacy_time = None
    event_from_spacy = None # Untuk menangkap event utama

    if nlp:
        doc = nlp(processed_text)
        for ent in doc.ents:
            if ent.label_ in ["DATE", "TIME"]: # SpaCy mengenali DATE/TIME
                try:
                    if ent.label_ == "DATE":
                        # Coba parse tanggal. Tanggal relatif (today, tomorrow) bisa jadi masalah di sini.
                        # Ini perlu penanganan lebih lanjut jika ingin presisi seperti regex sebelumnya.
                        # Untuk sekarang, akan mengandalkan SpaCy atau fallback regex.
                        temp_date = datetime.strptime(ent.text, '%Y-%m-%d').date() # Asumsi format standar
                        spacy_date = temp_date
                    elif ent.label_ == "TIME":
                        temp_time = datetime.strptime(ent.text, '%H:%M').time() # Asumsi format standar
                        spacy_time = temp_time
                    
                    # Jika entitas ditemukan, hapus dari processed_text untuk ekstraksi event/metadata
                    processed_text = processed_text.replace(ent.text, '').strip()
                except ValueError:
                    pass
            # Coba ekstrak event utama jika ada
            # Ini sangat tergantung pada model SpaCy dan jenis entitas yang dikenali
            # Contoh: jika ada entitas kustom 'ACTIVITY' atau 'TASK'
            # if ent.label_ == "TASK" or ent.label_ == "ACTIVITY":
            #     event_from_spacy = ent.text.strip()
            #     processed_text = processed_text.replace(ent.text, '').strip()

    # --- Fallback/Pelengkap untuk Tanggal dan Waktu (Regex yang sudah ada) ---
    if not spacy_date:
        # Ekstraksi keyword tanggal (hari ini, besok, dll.)
        date_keywords_map = {
            "hari ini": now_local.date(), "besok": (now_local + timedelta(days=1)).date(),
            "lusa": (now_local + timedelta(days=2)).date(), "minggu depan": (now_local + timedelta(weeks=1)).date(),
            "bulan depan": (now_local.replace(day=1) + timedelta(days=32)).replace(day=now_local.day).date()
        }
        for keyword, date_obj in date_keywords_map.items():
            if keyword in original_text_lower:
                scheduled_datetime_aware = scheduled_datetime_aware.replace(year=date_obj.year, month=date_obj.month, day=date_obj.day, tzinfo=scheduled_datetime_aware.tzinfo)
                processed_text = re.sub(re.escape(keyword), '', processed_text, flags=re.IGNORECASE).strip()
                break
        
        # Ekstraksi hari dalam seminggu
        day_of_week_map = {
            "senin": 0, "selasa": 1, "rabu": 2, "kamis": 3, "jumat": 4, "sabtu": 5, "minggu": 6
        }
        for day_name, day_num in day_of_week_map.items():
            if day_name in original_text_lower:
                days_ahead = (day_num - now_local.weekday() + 7) % 7
                if days_ahead == 0 and scheduled_datetime_aware.date() == now_local.date() and scheduled_datetime_aware.time() < now_local.time():
                    days_ahead = 7 # Jika hari ini sudah lewat, maju ke minggu depan
                elif days_ahead == 0 and scheduled_datetime_aware.date() == now_local.date() and scheduled_datetime_aware.time() >= now_local.time():
                    pass # Hari ini belum lewat
                elif days_ahead == 0 and scheduled_datetime_aware.date() != now_local.date():
                    pass # Jika sudah ditentukan tanggal lain (besok, lusa), jangan reset
                elif days_ahead == 0: # Ini berarti hari yang sama minggu depan (jika belum maju)
                     days_ahead = 7
                
                target_date = (now_local.date() if scheduled_datetime_aware.date() == now_local.date() else scheduled_datetime_aware.date()) + timedelta(days=days_ahead)
                scheduled_datetime_aware = scheduled_datetime_aware.replace(year=target_date.year, month=target_date.month, day=target_date.day, tzinfo=scheduled_datetime_aware.tzinfo)
                processed_text = re.sub(re.escape(day_name), '', processed_text, flags=re.IGNORECASE).strip()
                break

    # Jika SpaCy tidak mendapatkan waktu, coba regex
    if not spacy_time:
        time_pattern = r'\b(\d{1,2}([\.:]\d{2})?)\s*(pagi|siang|sore|malam|am|pm)?\b'
        time_match = re.search(time_pattern, original_text_lower, re.IGNORECASE)
        if time_match:
            try:
                time_str_raw = time_match.group(1)
                ampm_str = (time_match.group(3) or '').lower()
                hour_extracted, minute_extracted = (map(int, time_str_raw.split(':')) if ':' in time_str_raw else
                                                    map(int, time_str_raw.split('.')) if '.' in time_str_raw else
                                                    (int(time_str_raw), 0))
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
                
                scheduled_datetime_aware = scheduled_datetime_aware.replace(hour=hour_extracted, minute=minute_extracted, second=0, microsecond=0, tzinfo=scheduled_datetime_aware.tzinfo)
                processed_text = re.sub(time_pattern, '', processed_text, flags=re.IGNORECASE).strip()
            except (ValueError, TypeError):
                pass
    
    # Default ke 9 pagi jika tidak ada waktu yang terdeteksi
    if scheduled_datetime_aware.time() == now_local.time() and scheduled_datetime_aware.date() == now_local.date():
        default_hour, default_minute = 9, 0
        temp_time = scheduled_datetime_aware.replace(hour=default_hour, minute=default_minute, second=0, microsecond=0, tzinfo=scheduled_datetime_aware.tzinfo)
        if temp_time < now_local:
            temp_time += timedelta(days=1)
        scheduled_datetime_aware = temp_time


    # --- 3. Ekstraksi Pengulangan & Metadata Terstruktur ---
    repeat_type = "none"
    repeat_interval = 0

    # Pola pengulangan yang sudah ada
    monthly_repeat_pattern = r'(?:setiap|tiap)\s*(\d+)\s*bulan|(?:(\d+)\s*bulan\s*kedepan)'
    monthly_repeat_match = re.search(monthly_repeat_pattern, original_text_lower)
    if monthly_repeat_match:
        repeat_type = "monthly_interval"
        repeat_interval = int(monthly_repeat_match.group(1) or monthly_repeat_match.group(2))
        processed_text = re.sub(monthly_repeat_pattern, '', processed_text, flags=re.IGNORECASE).strip()

    yearly_repeat_pattern_explicit = r'(?:setiap|tiap)\s*(\d+)\s*tahun|(?:(\d+)\s*tahun\s*kedepan)'
    yearly_repeat_match_explicit = re.search(yearly_repeat_pattern_explicit, original_text_lower)
    if yearly_repeat_match_explicit:
        repeat_type = "yearly"
        repeat_interval = int(yearly_repeat_match_explicit.group(1) or yearly_repeat_match_explicit.group(2))
        processed_text = re.sub(yearly_repeat_pattern_explicit, '', processed_text, flags=re.IGNORECASE).strip()
    elif "setiap tahun" in original_text_lower or "tiap tahun" in original_text_lower:
        repeat_type = "yearly"
        repeat_interval = 1 
        processed_text = re.sub(r'setiap tahun|tiap tahun', '', processed_text, flags=re.IGNORECASE).strip()
    
    # NEW: Pola pengulangan Harian/Mingguan
    if "daily" in original_text_lower or "setiap hari" in original_text_lower or "tiap hari" in original_text_lower:
        repeat_type = "daily"
        repeat_interval = 1
        processed_text = re.sub(r'daily|setiap hari|tiap hari', '', processed_text, flags=re.IGNORECASE).strip()
    elif "mon/wed/fri" in original_text_lower: # Contoh spesifik
        repeat_type = "weekly_custom" # Ini perlu logika lebih kompleks di scheduler
        metadata["repeat_days"] = "Mon,Wed,Fri"
        processed_text = processed_text.replace("mon/wed/fri", "").strip()
    elif "sundays" in original_text_lower or "setiap minggu" in original_text_lower:
        repeat_type = "weekly"
        repeat_interval = day_of_week_map["minggu"] # Simpan hari target
        processed_text = re.sub(r'sundays|setiap minggu', '', processed_text, flags=re.IGNORECASE).strip()
    elif "tuesdays" in original_text_lower:
        repeat_type = "weekly"
        repeat_interval = day_of_week_map["selasa"] # Simpan hari target
        processed_text = processed_text.replace("tuesdays", "").strip()


    # Ekstraksi Metadata (menggunakan regex dan membersihkan teks)
    metadata = {}
    
    # Pola untuk metadata spesifik
    metadata_patterns = {
        "notes": r'(?:notes|catatan):\s*["“](.*?)[”"]|(?:notes|catatan):\s*(.+?)(?=\s*(?:mood:|suggestion:|saran:|$))',
        "mood": r'(?:mood|suasana hati):\s*([^\s]+)(?=\s*(?:notes:|catatan:|suggestion:|saran:|$))',
        "suggestion": r'(?:suggestion|saran):\s*(.+)',
        # Pola untuk aktivitas/item yang Anda sebutkan
        "activity_type": r'(gym|office day|online course|reading|groceries)', # Kata kunci untuk jenis aktivitas utama
        "favorite_meals": r'(favorite meals|makanan favorit):\s*(.+)',
        "coffee_preference": r'(coffee|kopi):\s*(.+)'
    }

    temp_processed_text = processed_text # Salinan untuk ekstraksi metadata
    for key, pattern in metadata_patterns.items():
        match = re.search(pattern, temp_processed_text, re.IGNORECASE)
        if match:
            # Handle groups for different patterns
            if key in ["notes", "favorite_meals", "coffee_preference", "suggestion"]: # These might have long content
                content = (match.group(1) or match.group(2) or match.group(0).split(':', 1)[1]).strip('"“’”').strip()
            elif key == "mood":
                content = match.group(1).strip()
            elif key == "activity_type":
                content = match.group(1).strip()
            else:
                content = match.group(0).strip() # Fallback for unmatched groups
            
            metadata[key] = content
            temp_processed_text = re.sub(pattern, '', temp_processed_text, flags=re.IGNORECASE).strip()
            
    # Bersihkan sisa processed_text setelah semua metadata diekstrak
    # Sisa ini akan menjadi dasar untuk event_title jika belum ditentukan oleh SpaCy
    clean_processed_text = re.sub(r'\s+', ' ', temp_processed_text).strip()

    # Tentukan event_title
    event_title = "Pengingat"
    if event_from_spacy: # Prioritaskan event dari SpaCy jika ada
        event_title = event_from_spacy
    elif 'activity_type' in metadata: # Prioritaskan dari metadata jika ada
        event_title = metadata['activity_type'].capitalize()
    elif clean_processed_text: # Fallback ke sisa teks
        event_title = clean_processed_text.split(' ')[0].capitalize() # Ambil kata pertama

    # Pastikan event_title tidak kosong atau hanya angka
    if not event_title or re.match(r'^\d+$', event_title):
        event_title = "Pengingat"
        # Jika event title masih "Pengingat" dan ada clean_processed_text yang signifikan, tambahkan ke metadata
        if clean_processed_text and clean_processed_text != "pengingat":
            metadata["description"] = clean_processed_text # Simpan sebagai deskripsi umum di metadata

    # --- 4. Validasi Akhir dan Konversi Zona Waktu ---
    tolerance = timedelta(seconds=2)
    
    if tz_matched: 
        scheduled_datetime_naive_temp = scheduled_datetime_aware.replace(tzinfo=None)
        scheduled_datetime_localized_target = target_tz.localize(scheduled_datetime_naive_temp)
        scheduled_datetime_final = scheduled_datetime_localized_target.astimezone(LOCAL_TIMEZONE)
    else:
        scheduled_datetime_final = scheduled_datetime_aware 

    # Ini penting: jika parsing tanggal/waktu gagal atau tidak menemukan apa-apa,
    # dan waktu default tidak maju, jangan buat pengingat
    if scheduled_datetime_final < now_local - tolerance:
        return None
    
    # Final check: is there actually meaningful data?
    if scheduled_datetime_final:
        return {
            "event": event_title,
            "datetime": scheduled_datetime_final,
            "repeat_type": repeat_type,
            "repeat_interval": repeat_interval,
            "metadata": metadata
        }
    return None


def extract_multiple_schedules(full_text):
    """
    Menguraikan beberapa pengingat dari satu blok teks input.
    Mencoba memecah teks berdasarkan pola waktu/tanggal atau baris.
    """
    now_local = datetime.now(LOCAL_TIMEZONE)
    # Ini adalah regex yang sangat kompleks, mencoba menemukan setiap instance waktu atau tanggal
    # agar kita bisa memecah teks berdasarkan itu.
    # Namun, ini akan sulit. Pendekatan yang lebih aman adalah memecah per baris.
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    
    parsed_reminders = []

    for line_text in lines:
        result = parse_single_schedule_fragment(line_text, now_local)
        if result:
            parsed_reminders.append(result)
            
    # Jika tidak ada pengingat yang ditemukan per baris, coba parsing seluruh teks sebagai satu event
    if not parsed_reminders and lines:
        single_result = parse_single_schedule_fragment(full_text, now_local)
        if single_result:
            parsed_reminders.append(single_result)

    return parsed_reminders


# --- API Endpoints ---
@app.route('/')
def serve_index():
    return render_template('index.html')

@app.route('/style.css')
def serve_css():
    return send_from_directory(current_dir, 'style.css')

@app.route('/script.js')
def serve_js():
    return send_from_directory(current_dir, 'script.js')

@app.route('/add_multiple_reminders', methods=['POST'])
def add_multiple_reminders_api():
    data = request.json
    full_note_text = data.get('full_note_text')
    user_id = data.get('user_id')

    if not full_note_text or not user_id:
        return jsonify({"success": False, "message": "Catatan pengingat atau User ID tidak boleh kosong."}), 400

    parsed_reminders = extract_multiple_schedules(full_note_text)

    if not parsed_reminders:
        return jsonify({"success": False, "message": "Tidak dapat mendeteksi pengingat dari catatan Anda. Coba format lain."}), 400

    added_count = 0
    for reminder_info in parsed_reminders:
        event = reminder_info['event']
        scheduled_time = reminder_info['datetime']
        repeat_type = reminder_info['repeat_type']
        repeat_interval = reminder_info['repeat_interval']
        metadata = json.dumps(reminder_info.get('metadata', {})) 

        insert_db('INSERT INTO reminders (user_id, event, metadata, datetime, repeat_type, repeat_interval, notified) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (user_id, event, metadata, scheduled_time.isoformat(), repeat_type, repeat_interval, 0))
        added_count += 1

    return jsonify({"success": True, "message": f"{added_count} pengingat berhasil ditambahkan."}), 200

@app.route('/get_reminders', methods=['GET'])
def get_reminders_api():
    user_id = request.args.get('user_id')

    if not user_id:
        return jsonify({"success": False, "message": "User ID tidak ditemukan."}), 400

    reminders = query_db('SELECT id, user_id, event, metadata, datetime, repeat_type, repeat_interval, notified FROM reminders WHERE user_id = ? ORDER BY datetime ASC', (user_id,))
    
    reminders_list = []
    for r in reminders:
        r_dict = dict(r)
        dt_obj = datetime.fromisoformat(r_dict['datetime'])
        r_dict['datetime'] = dt_obj.isoformat()
        r_dict['formatted_datetime'] = dt_obj.strftime(f'%d %B %Y %H:%M {format_timezone_display(dt_obj)}')
        r_dict['notified_status'] = "Selesai" if r_dict['notified'] else "Akan Datang"
        
        r_dict['metadata'] = json.loads(r_dict['metadata']) if r_dict['metadata'] else {}

        reminders_list.append(r_dict)
    
    return jsonify(reminders_list), 200

@app.route('/get_reminders_for_month', methods=['GET'])
def get_reminders_for_month():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    user_id = request.args.get('user_id')

    if not year or not month or not user_id:
        return jsonify({"error": "Missing year, month, or user_id parameter"}), 400

    start_date = datetime(year, month, 1, 0, 0, 0, tzinfo=LOCAL_TIMEZONE)
    if month == 12:
        end_date = datetime(year + 1, 1, 1, 23, 59, 59, tzinfo=LOCAL_TIMEZONE) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1, 23, 59, 59, tzinfo=LOCAL_TIMEZONE) - timedelta(days=1)
    
    reminders = query_db(
        'SELECT id, event, metadata, datetime FROM reminders WHERE user_id = ? AND datetime BETWEEN ? AND ? ORDER BY datetime ASC',
        (user_id, start_date.isoformat(), end_date.isoformat())
    )
    
    reminders_data = []
    for r in reminders:
        r_dict = dict(r)
        dt_obj = datetime.fromisoformat(r_dict['datetime'])
        reminders_data.append({
            'id': r_dict['id'],
            'event': r_dict['event'],
            'metadata': json.loads(r_dict['metadata']) if r_dict['metadata'] else {},
            'date': dt_obj.strftime('%Y-%m-%d')
        })
    
    return jsonify(reminders_data), 200

@app.route('/delete_reminder/<int:reminder_id>', methods=['DELETE'])
def delete_reminder_api(reminder_id):
    user_id = request.args.get('user_id')

    if not user_id:
        return jsonify({"success": False, "message": "User ID tidak ditemukan."}), 400

    cursor = get_db().execute('DELETE FROM reminders WHERE id = ? AND user_id = ?', (reminder_id, user_id))
    get_db().commit()
    if cursor.rowcount > 0:
        return jsonify({"success": True, "message": "Pengingat berhasil dihapus."}), 200
    else:
        return jsonify({"success": False, "message": "Pengingat tidak ditemukan atau Anda tidak memiliki izin untuk menghapusnya."}), 404

# --- Scheduler untuk Mengecek Pengingat Jatuh Tempo (perlu adaptasi untuk pengulangan baru) ---
def check_reminders_job():
    with app.app_context():
        now_local = datetime.now(LOCAL_TIMEZONE)
        
        reminders = query_db('SELECT * FROM reminders WHERE notified = 0 ORDER BY datetime ASC')

        for reminder_data in reminders:
            reminder_dt = datetime.fromisoformat(reminder_data['datetime'])
            
            if reminder_dt.tzinfo is None and now_local.tzinfo is not None:
                reminder_dt = LOCAL_TIMEZONE.localize(reminder_dt.replace(tzinfo=None))
            elif reminder_dt.tzinfo is not None and now_local.tzinfo is None:
                now_local = LOCAL_TIMEZONE.localize(now_local.replace(tzinfo=None))
            
            if now_local >= reminder_dt:
                print(f"Mengirim notifikasi (simulasi di log) untuk: {reminder_data['event']} (User: {reminder_data['user_id']}) pada {reminder_dt}")
                
                if reminder_data['repeat_type'] == 'none':
                    update_db('UPDATE reminders SET notified = 1 WHERE id = ?', (reminder_data['id'],))
                else:
                    next_datetime = reminder_dt
                    repeat_interval = reminder_data['repeat_interval'] # Untuk yearly/monthly
                    
                    if reminder_data['repeat_type'] == 'yearly':
                        next_datetime = next_datetime.replace(year=next_datetime.year + repeat_interval, tzinfo=next_datetime.tzinfo)
                    elif reminder_data['repeat_type'] == 'monthly_interval':
                        next_datetime = add_months(next_datetime, repeat_interval)
                    elif reminder_data['repeat_type'] == 'daily':
                        next_datetime += timedelta(days=1)
                    elif reminder_data['repeat_type'] == 'weekly': # Untuk pengulangan mingguan spesifik hari
                        # repeat_interval di sini adalah weekday number (0-6)
                        current_day_of_week = next_datetime.weekday() # 0=Senin, 6=Minggu
                        target_day_of_week = reminder_data['repeat_interval'] # Target day number (e.g., 6 for Sunday)
                        
                        days_to_advance = (target_day_of_week - current_day_of_week + 7) % 7
                        if days_to_advance == 0: # Jika hari ini adalah hari target, majukan 1 minggu
                            days_to_advance = 7
                        next_datetime += timedelta(days=days_to_advance)
                    elif reminder_data['repeat_type'] == 'weekly_custom': # Contoh Mon/Wed/Fri
                        # Ini adalah yang paling kompleks, memerlukan array hari di metadata
                        # Untuk demo, ini akan jadi PRT (perlu waktu)
                        # Anda bisa membiarkannya sebagai 'none' atau mengubah logika ini.
                        # Untuk saat ini, asumsikan next_datetime += timedelta(days=7) sebagai fallback
                        print("WARNING: 'weekly_custom' repeat type needs advanced logic for next_datetime calculation.")
                        next_datetime += timedelta(days=7) # Default maju 1 minggu
                        
                    # Maju cepat jika pengingat terlewat banyak kali
                    while next_datetime <= now_local:
                        if reminder_data['repeat_type'] == 'yearly':
                            next_datetime = next_datetime.replace(year=next_datetime.year + repeat_interval, tzinfo=next_datetime.tzinfo)
                        elif reminder_data['repeat_type'] == 'monthly_interval':
                            next_datetime = add_months(next_datetime, repeat_interval)
                        elif reminder_data['repeat_type'] == 'daily':
                            next_datetime += timedelta(days=1)
                        elif reminder_data['repeat_type'] == 'weekly':
                            next_datetime += timedelta(days=7) # Maju 1 minggu
                        elif reminder_data['repeat_type'] == 'weekly_custom':
                            next_datetime += timedelta(days=7) # Maju 1 minggu
                            
                    update_db('UPDATE reminders SET datetime = ?, notified = 0 WHERE id = ?', 
                              (next_datetime.isoformat(), reminder_data['id']))
        get_db().commit()
    
scheduler = BackgroundScheduler()
scheduler.add_job(check_reminders_job, IntervalTrigger(seconds=30), id='check_reminders', replace_existing=True)

if __name__ != '__main__':
    scheduler.start()
    print("Scheduler started in background for production.")

# --- Main Run Block ---
if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        from database import init_db
        init_db()
    
    scheduler.start()
    print("Scheduler started for local development.")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
