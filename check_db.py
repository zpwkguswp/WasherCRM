import sqlite3
import os

db_path = 'backend/washer_crm.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT name, is_approved, tier FROM branches WHERE manager_phone="01011112222"')
    row = cur.fetchone()
    print(f"Branch Info: {row}")
    conn.close()
else:
    print("Database not found.")
