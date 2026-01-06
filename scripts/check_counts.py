#!/usr/bin/env python3
import os
import sys
import psycopg2

# Allow passing DSN on the command line for reliability in PowerShell
if len(sys.argv) > 1:
    dsn = sys.argv[1]
else:
    dsn = os.environ.get('DATABASE_URL')
if not dsn:
    print('Usage: check_counts.py <POSTGRES_DSN> or set DATABASE_URL env var')
    raise SystemExit(2)

conn = psycopg2.connect(dsn)
cur = conn.cursor()
tables = ['invoices_invoice','invoices_invoiceitem','invoices_client','invoices_businessprofile','invoices_adclick','invoices','clients','invoice_items']
for t in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"{t}:", cur.fetchone()[0])
    except Exception as e:
        print(f"{t}: ERROR ({e})")

cur.close()
conn.close()
