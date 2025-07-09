import os
from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
import re
import pytz # Diperlukan untuk penanganan zona waktu


# --- INISIALISASI APLIKASI FLASK ---
app = Flask(__name__)

# --- KONFIGURASI ZONA WAKTU ---
# Di PythonAnywhere, server biasanya UTC. Di Railway juga.
# Kita akan tetap gunakan Asia/Jakarta untuk konversi input/output.
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

# --- FUNGSI NLP: extract_schedule (Inti AI) ---
# Ini adalah fungsi yang mengurai teks untuk menemukan jadwal.
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
    
    repeat_type = "none" # Fitur pengulangan tidak aktif di versi ini
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
    stopwords = ['ingatkan', 'saya', 'untuk', 'pada', 'di', 'tanggal', 'pukul', 'jam', 'paling lambat', 'mengingatkan', 'setelah', 'depan', 'setiap', 'tiap', 'ke depan', 'menit', 'lagi', 'dalam', 'kedepan', 'isya', 'subuh', 'dzuhur', 'ashar', 'maghrib', 'malam', 'sore', 'siang', 'pagi']
    words = event_description.split()
    final_event_description = ' '.join([word for word in words if word.lower() not in stopwords])
    final_event_description = final_event_description.replace("  ", " ").strip()

    if not final_event_description:
        final_event_description = "Pengingat"


    tolerance = timedelta(seconds=2)
    
    if scheduled_datetime_aware < now_local - tolerance:
        print(f"DEBUG: Waktu yang diekstrak ({scheduled_datetime_aware}) sudah lampau dari sekarang ({now_local}). Mengembalikan None.")
        return None 
    
    if scheduled_datetime_aware:
        return {"event": final_event_description, "datetime": scheduled_datetime_aware, "repeat_type": repeat_type, "repeat_interval": repeat_interval}
    return None

def format_timezone_display(dt_object):
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

@app.route('/set_reminder', methods=['POST'])
def set_reminder_api():
    # Menggunakan list global di memori, bukan database
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
        reminder_time=parsed_schedule['datetime'], # Ini sudah aware
        created_at=datetime.now(LOCAL_TIMEZONE),
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
                dt_obj_from_iso = datetime.fromisoformat(r_dict['reminder_time']) 
                tz_display = format_timezone_display(dt_obj_from_iso)
                if tz_display:
                    r_dict['reminder_time_display'] = dt_obj_from_iso.strftime(f'%d %B %Y %H:%M {tz_display}')
                else:
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
    # Tidak ada operasi database saat startup di versi ini
    port = int(os.getenv("PORT", 5000))
    print(f"INFO: Flask app running on port {port}")
    app.run(debug=True, host='0.0.0.0', port=port)
