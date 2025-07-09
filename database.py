import sqlite3

DATABASE = 'reminders.db'

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            event TEXT NOT NULL,          -- Tetap ada untuk judul utama
            metadata TEXT,                -- <<< KOLOM BARU UNTUK DATA TERSTRUKTUR (JSON STRING)
            datetime TEXT NOT NULL,
            repeat_type TEXT DEFAULT 'none',
            repeat_interval INTEGER DEFAULT 0,
            notified BOOLEAN DEFAULT 0
            -- Kolom description, notes, mood, suggestion dihapus
        )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()
