import sqlite3

conn = sqlite3.connect('database.db')
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    grade TEXT,
    section TEXT,
    school TEXT,
    phone TEXT,
    event_10_11 TEXT,
    event_11_12 TEXT,
    event_1_2 TEXT,
    event_2_3 TEXT,
    consent INTEGER,
    created_by INTEGER
)
""")

conn.commit()
conn.close()

print("✅ Students table created with grade + event slots")
