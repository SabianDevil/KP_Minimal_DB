import os
from datetime import datetime, timedelta
import re

# --- Impor Tool generic_reminders ---
# Asumsikan tools ini tersedia di lingkungan eksekusi (misalnya, di platform yang mendukungnya)
# Jika Anda menjalankan ini secara lokal atau di lingkungan tanpa integrasi tool,
# Anda perlu mengganti bagian ini dengan implementasi dummy atau API pengingat sungguhan.
# Untuk tujuan demonstrasi dan asumsi Railway/lingkungan serupa, kita akan memanggilnya secara langsung.

# --- Dummy GenericReminders API (Jika Anda menjalankan ini di luar lingkungan terintegrasi) ---
# Jika Anda menjalankan ini di lingkungan yang tidak memiliki tool generic_reminders
# secara native (seperti lokal PC Anda), Anda bisa menggunakan dummy ini untuk testing.
# Hapus atau komentar baris ini jika Anda menjalankannya di lingkungan yang menyediakan tool.
class GenericRemindersProvider:
    GOOGLE_TASKS = "google_tasks"

class Reminder:
    def __init__(self, id, title, schedule, completed=False):
        self.id = id
        self.title = title
        self.schedule = schedule
        self.completed = completed

class RemindersResult:
    def __init__(self, message, reminders=None):
        self.message = message
        self.reminders = reminders if reminders is not None else []

def create_reminder(title=None, description=None, start_date=None, time_of_day=None, am_pm_or_unknown=None, end_date=None, repeat_every_n=None, repeat_interval_unit=None, days_of_week=None, weeks_of_month=None, days_of_month=None, occurrence_count=None, provider=None):
    print(f"DEBUG: Dummy create_reminder called with: Title='{title}', Date='{start_date}', Time='{time_of_day}'")
    if not title:
        return RemindersResult(message="Error: Title is required for dummy reminder.", reminders=[])
    if not start_date or not time_of_day:
        return RemindersResult(message="Error: Date and Time are required for dummy reminder.", reminders=[])

    # Simulasi ID
    new_id = f"dummy-id-{datetime.now().timestamp()}"
    schedule_str = f"{start_date} {time_of_day}"
    
    dummy_reminder = Reminder(id=new_id, title=title, schedule=schedule_str)
    return RemindersResult(message=f"Dummy reminder '{title}' created for {schedule_str}", reminders=[dummy_reminder])

# --- Akhir Dummy GenericReminders API ---

# --- FUNGSI NLP: extract_schedule (disimplifikasi) ---
# Ini adalah versi yang disederhanakan dari fungsi extract_schedule yang kita kembangkan.
# Fokus pada deteksi dasar tanggal dan waktu.
def extract_schedule(text):
    original_text = text.lower()
    processed_text = original_text 
    
    now_local = datetime.now() # Naive datetime, tanpa zona waktu spesifik
    scheduled_datetime_naive = now_local 
    
    repeat_type = "none" # Default, tidak ada pengulangan di versi ini
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
                
                # Jika waktu yang diekstrak sudah lewat hari ini, pindahkan ke besok
                if temp_time < now_local and temp_time.date() == scheduled_datetime_naive.date():
                    temp_time += timedelta(days=1)

                scheduled_datetime_naive = temp_time
                found_time_set_by_match = True
                
                processed_text = re.sub(time_pattern, '', processed_text, flags=re.IGNORECASE).strip()
            except (ValueError, TypeError):
                pass

    if not found_time_set_by_match: # Jika tidak ada waktu spesifik, default ke jam 9 pagi besok
        default_hour = 9
        default_minute = 0
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
        final_event_description = "Pengingat" # Default jika tidak ada deskripsi lain

    # 4. Validasi Akhir dan Penyesuaian Waktu Lampau
    tolerance = timedelta(seconds=2) # Toleransi kecil untuk waktu saat ini
    
    if scheduled_datetime_naive < now_local - tolerance:
        print(f"DEBUG: Waktu yang diekstrak ({scheduled_datetime_naive}) sudah lampau dari sekarang ({now_local}). Mengembalikan None.")
        return None # Jangan membuat pengingat di masa lalu
    
    if scheduled_datetime_naive:
        return {"event": final_event_description, "datetime": scheduled_datetime_naive, "repeat_type": repeat_type, "repeat_interval": repeat_interval}
    return None


# --- Fungsi Utama untuk Membuat Pengingat ---
def create_ai_reminder(reminder_text):
    print(f"Menganalisis teks pengingat: '{reminder_text}'")
    parsed_schedule = extract_schedule(reminder_text)

    if not parsed_schedule:
        print("Gagal memahami jadwal pengingat dari teks yang diberikan.")
        return "Gagal membuat pengingat: Tidak dapat memahami jadwal atau waktu pengingat sudah lampau."

    title = parsed_schedule['event']
    # Format tanggal dan waktu untuk tool generic_reminders
    start_date = parsed_schedule['datetime'].strftime('%Y-%m-%d')
    time_of_day = parsed_schedule['datetime'].strftime('%H:%M:%S')

    print(f"Mencoba membuat pengingat: '{title}' pada {start_date} pukul {time_of_day}")

    try:
        # Panggil tool generic_reminders.create_reminder
        # Ambil am_pm_or_unknown dari waktu yang diekstrak jika ada, atau set UNKNOWN
        am_pm_or_unknown = "UNKNOWN" # Untuk versi dasar ini, kita asumsikan UNKNOWN
        
        result = create_reminder(
            title=title,
            start_date=start_date,
            time_of_day=time_of_day,
            am_pm_or_unknown=am_pm_or_unknown,
            provider=GenericRemindersProvider.GOOGLE_TASKS # Atau provider lain jika relevan
        )
        
        if result.message and "Error" in result.message:
            print(f"Error dari tool pengingat: {result.message}")
            return f"Gagal membuat pengingat: {result.message}"
        elif result.reminders:
            reminder_info = result.reminders[0]
            print(f"Pengingat berhasil dibuat! ID: {reminder_info.id}, Judul: '{reminder_info.title}', Jadwal: {reminder_info.schedule}")
            return f"Pengingat '{reminder_info.title}' berhasil diatur untuk {reminder_info.schedule}."
        else:
            print(f"Tool pengingat mengembalikan pesan: {result.message}")
            return f"Pengingat berhasil diatur: {result.message}"

    except Exception as e:
        print(f"Terjadi kesalahan saat memanggil tool pengingat: {e}")
        return f"Terjadi kesalahan internal saat membuat pengingat: {str(e)}"

# --- Contoh Penggunaan (Ini yang akan Anda jalankan di Railway) ---
if __name__ == "__main__":
    # Anda bisa mengganti teks ini dengan input dari mana pun (misal: API endpoint, message queue, dll.)
    reminder_input_text = "Ingatkan saya beli susu besok jam 7 pagi"
    # reminder_input_text = "Rapat tim jam 14:30 hari ini"
    # reminder_input_text = "Telepon ibu dalam 30 menit"
    # reminder_input_text = "Bayar tagihan listrik tanggal 25 Juli 2025"

    response = create_ai_reminder(reminder_input_text)
    print(f"\nHasil Akhir: {response}")

    # Anda bisa menambahkan lebih banyak contoh di sini
    print("\n--- Contoh Lain ---")
    response2 = create_ai_reminder("Kirim laporan jam 5 sore")
    print(f"Hasil Akhir 2: {response2}")

    response3 = create_ai_reminder("Olahraga lusa")
    print(f"Hasil Akhir 3: {response3}") # Waktu default 9 pagi akan digunakan
