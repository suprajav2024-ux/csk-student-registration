import sqlite3

conn = sqlite3.connect('database.db')
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    password TEXT
)
''')

# Insert only if not already inserted
try:
    c.execute("INSERT INTO teachers (name, email, password) VALUES (?, ?, ?)",
            ('Supraja V', 'supraja@example.com', 'test123'))
    conn.commit()
    print("✅ Teacher added successfully!")
except:
    print("⚠️ Teacher already exists or something went wrong.")

conn.close()
print("✅ Database created or already exists.")