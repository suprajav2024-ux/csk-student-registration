import sqlite3

conn = sqlite3.connect('database.db')
c = conn.cursor()

# Drop and recreate the table if needed
c.execute('DROP TABLE IF EXISTS students')

c.execute('''
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    class TEXT,
    section TEXT,
    school TEXT,
    phone TEXT,
    event_10_11 TEXT,
    event_11_12 TEXT,
    event_1_2 TEXT,
    event_2_3 TEXT,
    consent_file TEXT,
    created_by INTEGER,
    FOREIGN KEY (created_by) REFERENCES teachers(id)
)
''')

conn.commit()
conn.close()
print("✅ Updated students table created.")
