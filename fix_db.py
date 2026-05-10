import sqlite3
import os

db_path = 'backend/washer_crm.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    # tier 컬럼 추가
    cur.execute('ALTER TABLE branches ADD COLUMN tier TEXT DEFAULT "BRONZE"')
    print("Column 'tier' added.")
except sqlite3.OperationalError:
    print("Column 'tier' already exists.")

# 수원 지사 정보 업데이트 및 확인
cur.execute('UPDATE branches SET tier="BRONZE" WHERE manager_phone="01011112222" AND tier IS NULL')
conn.commit()

cur.execute('SELECT name, is_approved, tier FROM branches WHERE manager_phone="01011112222"')
print(f"Final Check: {cur.fetchone()}")

conn.close()
