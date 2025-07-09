from flask import Flask, request, jsonify, render_template, g, send_from_directory
from datetime import datetime, timedelta
import re
import pytz
import sqlite3
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import json

# --- Konfigurasi Flask dan Database ---
current_dir = os.getcwd()
app = Flask(__name__,
            template_folder=current_dir,
            static_folder=current_dir)

DATABASE = 'reminders.db'

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

# --- Logika AI Pengingat Anda (Kembali ke Regex-Only, tapi dengan Metadata & Multi-Reminder) ---
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

def parse_single_schedule_fragment(text_fragment, now_local_context):
    """
    Mencoba menguraikan satu pengingat dari fragmen teks menggunakan HANYA regex.
    `now_local_context` digunakan untuk tanggal/waktu relatif.
    """
    original_text_lower = text_fragment.lower()
    processed_text = text_fragment # Pertahankan casing asli untuk ekstraksi metadata jika perlu
    
    scheduled_datetime_aware = now_local_context
    target_tz = LOCAL_TIMEZONE
    tz_matched = False
    
    # --- 1. Ekstraksi Zona Waktu ---
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

    # --- 2. Ekstraksi Tanggal dan Waktu (HANYA Regex) ---
    
    # Ekstraksi relatif waktu (dalam jam/menit lagi)
    relative_time_pattern = r'\b(dalam\s+)?(\d+)\s*(jam|menit)\s*(lagi|ke\s+depan)?\b'
    relative_time_match = re.search(relative_time_pattern, original_text_lower, re.IGNORECASE)
    if relative_time_match:
        value = int(relative_time_match.group(2))
        unit = relative_time_match.group(3)
        if unit == "jam":
            scheduled_datetime_aware = now_local_context + timedelta(hours=value)
        elif unit == "menit":
            scheduled_datetime_aware = now_local_context + timedelta(minutes=value)
        processed_text = re.sub(relative_time_pattern, '', processed_text, flags=re.IGNORECASE).strip()
        
    # Ekstraksi waktu sholat
    waktu_sholat_map = {
        "subuh": "05:00", "dzuhur": "12:00", "ashar": "15:00", "maghrib": "18:00", "isya": "19:30"
    }
    for sholat_name, sholat_time_str in waktu_sholat_map.items():
        if sholat_name in original_text_lower:
            try:
                hour, minute = map(int, sholat_time_str.split(':'))
                temp_time = scheduled_datetime_aware.replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=scheduled_datetime_aware.tzinfo)
                if temp_time < now_local_context and temp_time.date() == scheduled_datetime_aware.date():
                    temp_time += timedelta(days=1)
                scheduled_datetime_aware = temp_time
                processed_text = re.sub(re.escape(sholat_name), '', processed_text, flags=re.IGNORECASE).strip()
                if f"setelah {sholat_name}" in original_text_lower:
                    scheduled_datetime_aware += timedelta(minutes=30)
                    processed_text = processed_text.replace(f"setelah {sholat_name}", "").strip()
                break
            except ValueError:
                pass
            
    # Ekstraksi waktu spesifik (jam:menit)
    time_pattern_regex = r'\b(jam |pukul )?(\d{1,2}([\.:]\d{2})?)\s*(pagi|siang|sore|malam|am|pm)?\b'
    time_match_regex = re.search(time_pattern_regex, original_text_lower, re.IGNORECASE)
    if time_match_regex:
        try:
            time_str_raw = time_match_regex.group(2)
            ampm_str = (time_match_regex.group(4) or '').lower()
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
            
            temp_datetime = scheduled_datetime_aware.replace(hour=hour_extracted, minute=minute_extracted, second=0, microsecond=0, tzinfo=scheduled_datetime_aware.tzinfo)
            if temp_datetime < now_local_context and temp_datetime.date() == scheduled_datetime_aware.date():
                temp_datetime += timedelta(days=1)
            scheduled_datetime_aware = temp_datetime
            processed_text = re.sub(time_pattern_regex, '', processed_text, flags=re.IGNORECASE).strip()
        except (ValueError, TypeError):
            pass
    
    # Default ke 9 pagi jika tidak ada waktu yang terdeteksi
    if scheduled_datetime_aware.time() == now_local_context.time() and scheduled_datetime_aware.date() == now_local_context.date():
        default_hour, default_minute = 9, 0
        temp_time = scheduled_datetime_aware.replace(hour=default_hour, minute=default_minute, second=0, microsecond=0, tzinfo=scheduled_datetime_aware.tzinfo)
        if temp_time < now_local_context:
            temp_time += timedelta(days=1)
        scheduled_datetime_aware = temp_time


    # Ekstraksi keyword tanggal (hari ini, besok, dll.)
    date_keywords_map = {
        "hari ini": now_local_context.date(), "besok": (now_local_context + timedelta(days=1)).date(),
        "lusa": (now_local_context + timedelta(days=2)).date(), "minggu depan": (now_local_context + timedelta(weeks=1)).date(),
        "bulan depan": (now_local_context.replace(day=1) + timedelta(days=32)).replace(day=now_local_context.day).date()
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
            days_ahead = (day_num - now_local_context.weekday() + 7) % 7
            if days_ahead == 0 and scheduled_datetime_aware.date() == now_local_context.date() and scheduled_datetime_aware.time() < now_local_context.time():
                days_ahead = 7
            elif days_ahead == 0 and scheduled_datetime_aware.date() == now_local_context.date() and scheduled_datetime_aware.time() >= now_local_context.time():
                pass
            elif days_ahead == 0 and scheduled_datetime_aware.date() != now_local_context.date():
                pass
            elif days_ahead == 0:
                 days_ahead = 7
            
            target_date = (now_local_context.date() if scheduled_datetime_aware.date() == now_local_context.date() else scheduled_datetime_aware.date()) + timedelta(days=days_ahead)
            scheduled_datetime_aware = scheduled_datetime_aware.replace(year=target_date.year, month=target_date.month, day=target_date.day, tzinfo=scheduled_datetime_aware.tzinfo)
            processed_text = re.sub(re.escape(day_name), '', processed_text, flags=re.IGNORECASE).strip()
            break

    # Ekstraksi tanggal spesifik (DD Month YYYY atau DD/MM/YYYY)
    date_pattern_regex = r'\b(\d{1,2}) (januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember) (\d{4})\b|\b(\d{1,2})/(\d{1,2})/(\d{4})\b'
    date_match_regex = re.search(date_pattern_regex, original_text_lower, re.IGNORECASE)
    if date_match_regex:
        try:
            parsed_date = None
            if date_match_regex.group(2):
                day_str, month_name, year_str = date_match_regex.group(1, 2, 3)
                bulan_map = {
                    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
                    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12
                }
                month_num = bulan_map.get(month_name.lower())
                if month_num:
                    parsed_date = datetime(int(year_str), month_num, int(day_str)).date()
            elif date_match_regex.group(4):
                day_str, month_str, year_str = date_match_regex.group(4, 5, 6)
                parsed_date = datetime(int(year_str), int(month_str), int(day_str)).date()

            if parsed_date:
                scheduled_datetime_aware = scheduled_datetime_aware.replace(year=parsed_date.year, month=parsed_date.month, day=parsed_date.day, tzinfo=scheduled_datetime_aware.tzinfo)
                processed_text = re.sub(date_pattern_regex, '', processed_text, flags=re.IGNORECASE).strip()
        except (ValueError, TypeError):
            pass

    # --- 3. Ekstraksi Pengulangan & Metadata Terstruktur (HANYA Regex) ---
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
    
    mon_wed_fri_match = re.search(r'mon/wed/fri', original_text_lower, re.IGNORECASE)
    if mon_wed_fri_match:
        repeat_type = "weekly_custom" # Ini perlu logika lebih kompleks di scheduler
        metadata["repeat_days"] = "Mon,Wed,Fri"
        processed_text = processed_text.replace(mon_wed_fri_match.group(0), "").strip()
    
    for day_name_key, day_num_val in day_of_week_map.items():
        if f"{day_name_key}s" in original_text_lower: # For "Sundays", "Tuesdays"
            repeat_type = "weekly"
            repeat_interval = day_num_val # Store the weekday number (0=Mon, 6=Sun)
            processed_text = processed_text.replace(f"{day_name_key}s", "").strip()
            break
        
    # Ekstraksi Metadata (menggunakan regex dan membersihkan teks)
    metadata = {}
    
    # Pola untuk metadata spesifik
    metadata_patterns = {
        "notes": r'(?:notes|catatan):\s*["“](.*?)[”"]|(?:notes|catatan):\s*(.+?)(?=\s*(?:mood:|suasana hati:|suggestion:|saran:|$))',
        "mood": r'(?:mood|suasana hati):\s*([^\s]+)(?=\s*(?:notes:|catatan:|suggestion:|saran:|$))',
        "suggestion": r'(?:suggestion|saran):\s*(.+)',
        # Pola untuk aktivitas/item yang Anda sebutkan
        "activity_type": r'(gym|online course|reading|groceries|in-office day|standup)', # Kata kunci untuk jenis aktivitas utama
        "favorite_meals": r'(?:favorite meals|makanan favorit):\s*(.+)',
        "coffee_preference": r'(?:coffee|kopi):\s*(.+)'
    }

    temp_processed_text_for_metadata = processed_text # Salinan untuk ekstraksi metadata
    for key, pattern in metadata_patterns.items():
        match = re.search(pattern, temp_processed_text_for_metadata, re.IGNORECASE)
        if match:
            # Handle groups for different patterns
            if key in ["notes", "favorite_meals", "coffee_preference", "suggestion"]:
                content = (match.group(1) or match.group(2) or match.group(0).split(':', 1)[1]).strip('"“’”').strip()
            elif key == "mood":
                content = match.group(1).strip()
            elif key == "activity_type": # For "gym", "in-office day", etc.
                content = match.group(1).strip()
            else:
                content = match.group(0).strip()
            
            metadata[key] = content
            temp_processed_text_for_metadata = re.sub(pattern, '', temp_processed_text_for_metadata, flags=re.IGNORECASE).strip()
            
    # Bersihkan sisa temp_processed_text_for_metadata setelah semua metadata diekstrak
    clean_remaining_text = re.sub(r'\s+', ' ', temp_processed_text_for_metadata).strip()


    # Tentukan event_title (prioritas dari activity_type atau kata pertama yang tersisa)
    event_title = "Pengingat"
    
    if 'activity_type' in metadata: # Prioritaskan dari metadata activity_type
        event_title = metadata['activity_type'].capitalize()
    elif clean_remaining_text: # Fallback ke sisa teks setelah ekstraksi
        event_title = clean_remaining_text.split(' ')[0].capitalize() # Ambil kata pertama
    
    # Pastikan event_title tidak kosong atau hanya angka
    if not event_title or re.match(r'^\d+$', event_title):
        event_title = "Pengingat"
        if clean_remaining_text and clean_remaining_text != "pengingat":
            metadata["description_fallback"] = clean_remaining_text # Simpan sebagai deskripsi umum di metadata


    # --- 4. Validasi Akhir dan Konversi Zona Waktu ---
    tolerance = timedelta(seconds=2)
    
    if tz_matched: 
        scheduled_datetime_naive_temp = scheduled_datetime_aware.replace(tzinfo=None)
        scheduled_datetime_localized_target = target_tz.localize(scheduled_datetime_naive_temp)
        scheduled_datetime_final = scheduled_datetime_localized_target.astimezone(LOCAL_TIMEZONE)
    else:
        scheduled_datetime_final = scheduled_datetime_aware 

    if scheduled_datetime_final < now_local_context - tolerance:
        return None
    
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
    Memecah teks berdasarkan baris dan mencoba menguraikan setiap fragmen.
    """
    now_local = datetime.now(LOCAL_TIMEZONE)
    
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    
    parsed_reminders = []

    for line_text in lines:
        result = parse_single_schedule_fragment(line_text, now_local)
        if result:
            parsed_reminders.append(result)
            
    # Fallback: Jika tidak ada pengingat yang ditemukan dari baris individual,
    # coba parsing seluruh teks sebagai satu event utama.
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

# --- Scheduler untuk Mengecek Pengingat Jatuh Tempo ---
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
                    repeat_interval = reminder_data['repeat_interval']
                    
                    if reminder_data['repeat_type'] == 'yearly':
                        next_datetime = next_datetime.replace(year=next_datetime.year + repeat_interval, tzinfo=next_datetime.tzinfo)
                    elif reminder_data['repeat_type'] == 'monthly_interval':
                        next_datetime = add_months(next_datetime, repeat_interval)
                    elif reminder_data['repeat_type'] == 'daily':
                        next_datetime += timedelta(days=1)
                    elif reminder_data['repeat_type'] == 'weekly':
                        # Untuk weekly, repeat_interval menyimpan weekday number (0=Senin, 6=Minggu)
                        current_day_of_week = next_datetime.weekday()
                        target_day_of_week = repeat_interval
                        
                        days_to_advance = (target_day_of_week - current_day_of_week + 7) % 7
                        if days_to_advance == 0:
                            if next_datetime.time() <= now_local.time():
                                days_to_advance = 7
                            else:
                                days_to_advance = 0
                        
                        next_datetime += timedelta(days=days_to_advance)

                    elif reminder_data['repeat_type'] == 'weekly_custom':
                        # Ini adalah yang paling kompleks, memerlukan array hari di metadata
                        metadata_obj = json.loads(reminder_data['metadata'])
                        repeat_days_str = metadata_obj.get("repeat_days")
                        if repeat_days_str:
                            day_map_str_to_int = {"mon":0, "tue":1, "wed":2, "thu":3, "fri":4, "sat":5, "sun":6}
                            target_weekdays = sorted([day_map_str_to_int[d.lower()] for d in repeat_days_str.split(',') if d.lower() in day_map_str_to_int])
                            
                            if target_weekdays:
                                current_weekday = next_datetime.weekday()
                                found_next_day = False
                                
                                # Cari hari berikutnya dalam minggu yang sama atau minggu depan
                                for target_day in target_weekdays:
                                    # Jika target_day lebih besar dari hari ini, atau jika target_day sama dengan hari ini TAPI waktu belum lewat
                                    if target_day > current_weekday or \
                                       (target_day == current_weekday and next_datetime.time() >= now_local.time()):
                                        days_to_advance = target_day - current_weekday
                                        next_datetime += timedelta(days=days_to_advance)
                                        found_next_day = True
                                        break
                                
                                if not found_next_day: # Maju ke minggu depan, ambil hari pertama dari daftar
                                    days_to_advance = (target_weekdays[0] - current_weekday + 7) % 7
                                    next_datetime += timedelta(days=days_to_advance)
                                
                            else: # Fallback jika repeat_days tidak valid
                                next_datetime += timedelta(days=7) 
                        else:
                            next_datetime += timedelta(days=7) 
                            
                    # Maju cepat jika pengingat terlewat banyak kali (penting untuk server yang down lama)
                    while next_datetime <= now_local:
                        if reminder_data['repeat_type'] == 'yearly':
                            next_datetime = next_datetime.replace(year=next_datetime.year + repeat_interval, tzinfo=next_datetime.tzinfo)
                        elif reminder_data['repeat_type'] == 'monthly_interval':
                            next_datetime = add_months(next_datetime, repeat_interval)
                        elif reminder_data['repeat_type'] == 'daily':
                            next_datetime += timedelta(days=1)
                        elif reminder_data['repeat_type'] == 'weekly':
                            next_datetime += timedelta(days=7)
                        elif reminder_data['repeat_type'] == 'weekly_custom':
                            # Untuk advance-multiple-skip logic, ini akan kompleks.
                            # Cukup maju 1 minggu per iterasi untuk ini.
                            next_datetime += timedelta(weeks=1) 
                            
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
