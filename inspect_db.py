import sqlite3
import os

db_path = "d:/crawlai_updated_2026/crawl_state_updated.db"

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Status Counts:")
cursor.execute("SELECT status, COUNT(*) FROM urls GROUP BY status")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\nRecent 10 processed/processing URLs:")
cursor.execute("SELECT url, status, last_updated FROM urls WHERE status != 'pending' ORDER BY last_updated DESC LIMIT 10")
for row in cursor.fetchall():
    print(f"  {row[1]} | {row[2]} | {row[0]}")

conn.close()
