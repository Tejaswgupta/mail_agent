import sqlite3
from pathlib import Path
import json

db_path = Path("mail_agent.db")
if not db_path.exists():
    print("Database not found!")
    exit()

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

print("--- EMAILS ---")
for row in conn.execute("SELECT * FROM processed_emails"):
    print(dict(row))

print("\n--- ATTACHMENTS ---")
for row in conn.execute("SELECT * FROM attachments"):
    print(dict(row))

print("\n--- PARSED XLSX ROWS ---")
for row in conn.execute("SELECT attachment_id, sheet_name, count(*) as count FROM xlsx_rows GROUP BY attachment_id, sheet_name"):
    print(dict(row))
    
print("\n--- FIRST 2 XLSX DATA ROWS ---")
for row in conn.execute("SELECT * FROM xlsx_rows LIMIT 2"):
    d = dict(row)
    # truncate data for printing
    d['data'] = d['data'][:100] + '...' if len(d['data']) > 100 else d['data']
    print(d)

print("\n--- PARSED PDF TABLES ---")
for row in conn.execute("SELECT attachment_id, page_number, count(*) as tables FROM pdf_tables GROUP BY attachment_id, page_number"):
    print(dict(row))

conn.close()
