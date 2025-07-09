import os
from flask import Flask, request, jsonify, render_template_string # render_template_string diimpor di sini
from datetime import datetime, timedelta
import re
import pytz 
import uuid 

# --- INISIALISASI APLIKASI FLASK ---
app = Flask(__name__)

# --- PENYIMPANAN PENGINGAT DI MEMORI (TIDAK PERSISTEN) ---
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

# --- MODEL PENGINGAT (Sederhana untuk memori) ---
class Reminder:
    def __init__(self, id, user_id, text, reminder_time, created_at, is_completed, repeat_type, repeat_interval):
        self.id = id
        self.user_id = user_id
        self.text = text
        self.reminder_time = reminder_time 
        self.created_at = created_at
        self.is_completed = is_completed
        self.repeat_type = repeat_type
        self.repeat_interval = repeat_interval

    def to_dict(self):
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
def extract_schedule(text):
    original_text = text.lower()
    processed_text = original_text 
    
    now_local = datetime.now(LOCAL_TIMEZONE) 
    scheduled_datetime_aware = now_local 
    
    default_hour, default_minute = 9, 0

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
    stopwords = ['ingatkan', 'saya', 'untuk', 'pada', 'di', 'tanggal', 'pukul', 'jam', 'paling lambat', 'mengingatkan', 'setelah', 'depan', 'setiap', 'tiap', 'ke depan', 'menit', 'lagi', 'dalam', 'kedepan', 'isya', 'subuh', 'dzuhur', 'ashar', 'maghrib', 'malam', 'sore', 'siang', 'pagi', 'minggu', 'senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu', 'bulan', 'tahun']
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

# --- ROUTE UTAMA FLASK (untuk menyajikan HTML/CSS/JS inline) ---
@app.route('/')
def index():
    # Ini adalah HTML, CSS, dan JavaScript yang disajikan langsung dari Python
    # Tidak perlu folder templates/ atau static/
    return render_template_string(HTML_CONTENT)

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

    new_reminder_obj = Reminder(
        id=str(uuid.uuid4()), 
        user_id="default_user",
        text=parsed_schedule['event'],
        reminder_time=parsed_schedule['datetime'], # Ini sudah aware
        created_at=datetime.now(LOCAL_TIMEZONE),
        is_completed=False,
        repeat_type=parsed_schedule['repeat_type'],
        repeat_interval=parsed_schedule['repeat_interval']
    )
    
    reminders_in_memory.append(new_reminder_obj)
    reminders_in_memory.sort(key=lambda r: r.reminder_time)

    print(f"DEBUG: Pengingat baru ditambahkan ke memori: {new_reminder_obj.to_dict()}")
    return jsonify({"message": "Pengingat berhasil diatur (disimpan di memori)!", "reminder": new_reminder_obj.to_dict()}), 201


@app.route('/get_reminders', methods=['GET'])
def get_reminders_api():
    # Menggunakan list global di memori, bukan database
    global reminders_in_memory
    
    print("DEBUG: Memulai get_reminders_api (dari memori).")
    
    reminders_data = []
    for r_obj in reminders_in_memory:
        try:
            r_dict = r_obj.to_dict() 
            
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
            pass 

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
    print("--- Memulai Aplikasi Flask AI Pengingat ---")
    port = int(os.getenv("PORT", 5000))
    print(f"INFO: Flask app running on port {port}")
    app.run(debug=False, host='0.0.0.0', port=port)

# --- HTML, CSS, JavaScript (Inline Content) ---
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Reminder App</title>
    <style>
        /* CSS Lengkap */
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            min-height: 100vh;
            margin: 0;
            background-color: #e0f2f7;
            padding: 20px;
            box-sizing: border-box;
            color: #333;
        }

        .main-wrapper {
            background-color: #ffffff;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
            text-align: center;
            width: 100%;
            max-width: 800px; /* Lebar lebih sempit karena tidak ada kalender */
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        header {
            margin-bottom: 20px;
        }

        h1 {
            color: #2c3e50;
            margin-bottom: 10px;
            font-size: 2.5em;
        }

        h2 {
            color: #34495e;
            margin-top: 25px;
            margin-bottom: 15px;
            font-size: 1.6em;
        }

        .input-section, .reminder-list-section {
            border: 1px solid #b3e0ff;
            padding: 20px;
            border-radius: 10px;
            background-color: #f0faff;
            box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.05);
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        textarea {
            width: calc(100% - 24px);
            padding: 12px;
            margin-bottom: 15px;
            border: 1px solid #99d6ff;
            border-radius: 6px;
            font-size: 1em;
            box-sizing: border-box;
            resize: vertical;
            min-height: 120px;
        }

        button {
            background-color: #007bff;
            color: white;
            padding: 12px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            width: 100%;
            font-size: 1.1em;
            transition: background-color 0.3s ease;
            margin-bottom: 10px;
        }

        button:hover {
            background-color: #0056b3;
        }

        .message-area {
            margin-top: 15px;
            padding: 12px;
            border-radius: 6px;
            display: none;
            font-weight: bold;
            font-size: 0.95em;
            text-align: left;
            white-space: pre-wrap; /* For error messages */
        }

        .message-area.success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }

        .message-area.error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }

        .message-area.visible {
            display: block;
        }

        #reminderList {
            list-style: none;
            padding: 0;
            margin: 0;
            max-height: 350px;
            overflow-y: auto;
            border: 1px solid #cce5ff;
            padding: 15px;
            border-radius: 8px;
            background-color: #ffffff;
        }

        #reminderList li {
            background-color: #e9f7fe;
            margin-bottom: 10px;
            padding: 12px 15px;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border: 1px solid #b3e0ff;
            word-wrap: break-word;
            white-space: normal;
        }

        #reminderList li.completed {
            background-color: #d4edda;
            text-decoration: line-through;
            color: #6c757d;
        }

        #reminderList li span.reminder-text {
            flex-grow: 1;
            margin-right: 10px;
        }

        #reminderList li .reminder-actions {
            display: flex;
            gap: 8px;
        }

        #reminderList li .reminder-actions button {
            width: auto;
            padding: 6px 10px;
            font-size: 0.85em;
            margin-bottom: 0;
        }

        #reminderList li .reminder-actions .complete-btn {
            background-color: #28a745;
        }
        #reminderList li .reminder-actions .complete-btn:hover {
            background-color: #218838;
        }
        #reminderList li .reminder-actions .delete-btn {
            background-color: #dc3545;
        }
        #reminderList li .reminder-actions .delete-btn:hover {
            background-color: #c82333;
        }

        /* Kalender dan Timezone Clocks dihapus dari sini untuk kesederhanaan */
        .calendar-section, .timezone-clocks { display: none; }
    </style>
    <script>
        // JavaScript Lengkap (disesuaikan untuk tidak menggunakan FullCalendar)
        document.addEventListener('DOMContentLoaded', () => {
            const reminderTextarea = document.getElementById('reminderText');
            const setReminderBtn = document.getElementById('setReminderBtn');
            const reminderMessageArea = document.getElementById('reminderMessageArea');
            const reminderList = document.getElementById('reminderList');
            // calendarEl dan calendar dihapus dari sini

            const DEFAULT_USER_ID = "default_user";

            function showMessage(messageAreaElement, message, type) {
                messageAreaElement.textContent = message;
                messageAreaElement.className = `message-area visible ${type}`;
                setTimeout(() => {
                    messageAreaElement.classList.remove('visible');
                }, 5000);
            }

            async function sendRequest(url, method, body = null) {
                try {
                    const options = {
                        method: method,
                        headers: {
                            'Content-Type': 'application/json',
                        },
                    };
                    if (body) {
                        options.body = JSON.stringify(body);
                    }

                    const response = await fetch(url, options);
                    const data = await response.json();

                    if (!response.ok) {
                        throw new Error(data.error || 'Terjadi kesalahan pada server.');
                    }
                    return data;
                } catch (error) {
                    console.error('Request failed:', error);
                    throw error;
                }
            }

            function renderReminders(reminders) {
                reminderList.innerHTML = '';
                if (reminders.length === 0) {
                    reminderList.innerHTML = '<li>Belum ada pengingat.</li>';
                    return;
                }

                reminders.forEach(r => {
                    const listItem = document.createElement('li');
                    listItem.dataset.id = r.id;
                    if (r.is_completed) {
                        listItem.classList.add('completed');
                    }

                    const reminderDetails = document.createElement('span');
                    reminderDetails.classList.add('reminder-text');

                    const reminderTime = r.reminder_time_display ? r.reminder_time_display : 'Waktu tidak diketahui';

                    reminderDetails.innerHTML = `<strong>${r.text}</strong><br><small>${reminderTime} (${r.repeat_type !== 'none' ? r.repeat_type : 'Sekali'})</small>`;
                    listItem.appendChild(reminderDetails);

                    const actionsDiv = document.createElement('div');
                    actionsDiv.classList.add('reminder-actions');

                    if (!r.is_completed) {
                        const completeBtn = document.createElement('button');
                        completeBtn.textContent = 'Selesai';
                        completeBtn.classList.add('complete-btn');
                        completeBtn.addEventListener('click', async () => {
                            try {
                                await sendRequest(`/complete_reminder/${r.id}`, 'POST');
                                showMessage(reminderMessageArea, 'Pengingat ditandai selesai!', 'success');
                                loadReminders();
                            } catch (error) {
                                showMessage(reminderMessageArea, `Gagal menandai selesai: ${error.message}`, 'error');
                            }
                        });
                        actionsDiv.appendChild(completeBtn);
                    }

                    const deleteBtn = document.createElement('button');
                    deleteBtn.textContent = 'Hapus';
                    deleteBtn.classList.add('delete-btn');
                    deleteBtn.addEventListener('click', async () => {
                        if (confirm('Anda yakin ingin menghapus pengingat ini?')) {
                            try {
                                await sendRequest(`/delete_reminder/${r.id}`, 'DELETE');
                                showMessage(reminderMessageArea, 'Pengingat berhasil dihapus!', 'success');
                                loadReminders();
                            } catch (error) {
                                showMessage(reminderMessageArea, `Gagal menghapus: ${error.message}`, 'error');
                            }
                        }
                    });
                    actionsDiv.appendChild(deleteBtn);

                    listItem.appendChild(actionsDiv);
                    reminderList.appendChild(listItem);
                });
            }

            // Kalender dihapus dari sini
        }

        async function loadReminders() {
            reminderList.innerHTML = '<li>Memuat pengingat...</li>';
            // Kalender dihapus dari sini
            try {
                const reminders = await sendRequest('/get_reminders', 'GET');
                renderReminders(reminders);
                // initializeCalendar(reminders) dihapus dari sini
                showMessage(reminderMessageArea, `Pengingat berhasil dimuat.`, 'success');
            } catch (error) {
                reminderList.innerHTML = `<li>Gagal memuat pengingat: ${error.message}</li>`;
                // Kalender dihapus dari sini
                showMessage(reminderMessageArea, `Gagal memuat pengingat. Cek koneksi server: ${error.message}`, 'error');
            }
        }

        // --- Event Listeners ---
        setReminderBtn.addEventListener('click', async () => {
            const text = reminderTextarea.value.trim();
            if (!text) {
                showMessage(reminderMessageArea, 'Teks pengingat tidak boleh kosong.', 'error');
                return;
            }

            try {
                const result = await sendRequest('/set_reminder', 'POST', { text, user_id: DEFAULT_USER_ID });
                showMessage(reminderMessageArea, result.message, 'success');
                reminderTextarea.value = '';
                loadReminders();
            } catch (error) {
                showMessage(reminderMessageArea, `Gagal mengatur pengingat: ${error.message}`, 'error');
            }
        });

        // Panggil saat halaman dimuat
        loadReminders();
    });
    </script>
</body>
</html>
"""

### 2. File `requirements.txt`

Pastikan `requirements.txt` Anda berisi kedua *library* ini:

**Salin *seluruh kode* ini dan tempelkan ke file `requirements.txt` Anda.**
