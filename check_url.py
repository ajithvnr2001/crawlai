import sqlite3
import os

db_path = "d:/crawlai_updated_2026/crawl_state_updated.db"
target_url = "https://forum.rclone.org/t/mounting-rclone-to-use-like-a-local-drive/25604/19"

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT status, last_updated FROM urls WHERE url = ?", (target_url,))
row = cursor.fetchone()

if row:
    print(f"URL: {target_url}")
    print(f"Status: {row[0]}")
    print(f"Last Updated: {row[1]}")
else:
    print(f"URL not found in database: {target_url}")
    
    # Try searching for partial URL to see if a similar one exists
    base_url = target_url.rsplit('/', 1)[0]
    print(f"\nSearching for other parts of the same topic ({base_url})...")
    cursor.execute("SELECT url, status FROM urls WHERE url LIKE ? LIMIT 5", (f"{base_url}%",))
    rows = cursor.fetchall()
    if rows:
        for r in rows:
            print(f"  {r[1]:<15} | {r[0]}")
    else:
        print("  No similar URLs found.")

conn.close()
