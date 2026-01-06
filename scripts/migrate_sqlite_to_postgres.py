#!/usr/bin/env python3
"""
Lightweight data migration script: copies data from the existing SQLite DB
into the PostgreSQL schema created by `pg_create_tables.sql`.

Usage:
  python scripts/migrate_sqlite_to_postgres.py --sqlite db.sqlite3 --postgres "postgresql://user:pass@host:5432/db"

Notes:
 - Run Django migrations on the Postgres DB first so `auth_user` and other Django
   tables exist.
 - This script attempts to preserve primary keys when possible and will set
   sequences to the correct next values.
 - Test on a copy of your databases first.
"""

import argparse
import sqlite3
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--sqlite', required=True, help='Path to sqlite db file')
    p.add_argument('--postgres', required=True, help='Postgres DATABASE_URL')
    return p.parse_args()


def pg_connect(dsn):
    # allow both full libpq-style and postgres:// URIs
    return psycopg2.connect(dsn)


def copy_business_profiles(sqlite_conn, pg_conn):
    cur = sqlite_conn.cursor()
    cur.execute('SELECT id, user_id, business_name, logo, address, city, state, zip_code, country, email, phone, created_at FROM invoices_businessprofile')
    rows = cur.fetchall()
    pgcur = pg_conn.cursor()
    for r in rows:
        (id_, user_id, business_name, logo, address, city, state, zip_code, country, email, phone, created_at) = r
        pgcur.execute('''
            INSERT INTO business_profiles(user_id, business_name, business_logo, business_address, street, city, state, zip, country, email, phone, created_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (user_id) DO UPDATE SET
              business_name = EXCLUDED.business_name,
              business_logo = EXCLUDED.business_logo,
              business_address = EXCLUDED.business_address,
              street = EXCLUDED.street,
              city = EXCLUDED.city,
              state = EXCLUDED.state,
              zip = EXCLUDED.zip,
              country = EXCLUDED.country,
              email = EXCLUDED.email,
              phone = EXCLUDED.phone,
              created_date = COALESCE(business_profiles.created_date, EXCLUDED.created_date)
        ''', (user_id, business_name, logo, address, None, city, state, zip_code, country, email, phone, created_at))
    pg_conn.commit()


def copy_clients(sqlite_conn, pg_conn):
    cur = sqlite_conn.cursor()
    cur.execute('SELECT id, user_id, name, email, phone, address, street, city, state, zip_code, country, created_at FROM invoices_client')
    rows = cur.fetchall()
    # compute totals per client from sqlite invoices
    inv_cur = sqlite_conn.cursor()
    pgcur = pg_conn.cursor()
    for r in rows:
        (id_, user_id, name, email, phone, address, street, city, state, zip_code, country, created_at) = r
        inv_cur.execute('SELECT COUNT(*), COALESCE(SUM(total_amount),0) FROM invoices_invoice WHERE client_id = ?', (id_,))
        cnt, total = inv_cur.fetchone()
        pgcur.execute('''
            INSERT INTO clients(client_id, user_id, client_business_or_person_name, client_email, client_phone, client_address, created_date, total_invoices_sent, total_amount_invoiced)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (client_id) DO UPDATE SET
              client_business_or_person_name = EXCLUDED.client_business_or_person_name,
              client_email = EXCLUDED.client_email,
              client_phone = EXCLUDED.client_phone
        ''', (id_, user_id, name, email, phone, address, created_at, cnt, total))
    pg_conn.commit()


def copy_invoices(sqlite_conn, pg_conn):
    cur = sqlite_conn.cursor()
    cur.execute('''SELECT id, user_id, client_id, invoice_number, invoice_date, due_date, status, subtotal, tax_rate, tax_amount, discount_amount, total_amount, currency, payment_terms, notes, created_at
                   FROM invoices_invoice''')
    rows = cur.fetchall()
    pgcur = pg_conn.cursor()
    for r in rows:
        (id_, user_id, client_id, invoice_number, invoice_date, due_date, status, subtotal, tax_rate, tax_amount, discount_amount, total_amount, currency, payment_terms, notes, created_at) = r
        pgcur.execute('''
            INSERT INTO invoices(invoice_id, user_id, client_id, invoice_number, invoice_date, due_date, status, subtotal, tax_rate, tax_amount, discount_amount, total_amount, currency, payment_terms, notes, created_timestamp, last_modified_timestamp, pdf_generated)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (invoice_id) DO UPDATE SET
               invoice_number = EXCLUDED.invoice_number
        ''', (id_, user_id, client_id, invoice_number, invoice_date, due_date, status, subtotal or 0, tax_rate or 0, tax_amount or 0, discount_amount or 0, total_amount or 0, currency, payment_terms, notes, created_at, created_at, False))
    pg_conn.commit()


def copy_invoice_items(sqlite_conn, pg_conn):
    cur = sqlite_conn.cursor()
    cur.execute('SELECT id, invoice_id, description, quantity, unit_price, line_total FROM invoices_invoiceitem')
    rows = cur.fetchall()
    pgcur = pg_conn.cursor()
    order_map = {}
    for r in rows:
        (id_, invoice_id, description, quantity, unit_price, line_total) = r
        order_map.setdefault(invoice_id, 0)
        item_order = order_map[invoice_id]
        order_map[invoice_id] += 1
        pgcur.execute('''
            INSERT INTO invoice_items(item_id, invoice_id, item_description, quantity, unit_price, line_total, item_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (item_id) DO UPDATE SET item_description = EXCLUDED.item_description
        ''', (id_, invoice_id, description, quantity or 0, unit_price or 0, line_total or 0, item_order))
    pg_conn.commit()


def copy_ad_clicks(sqlite_conn, pg_conn):
    # invoices_adclick current schema: ad_identifier, placement, user, session_id, ip_address, target_url, timestamp
    cur = sqlite_conn.cursor()
    cur.execute('SELECT id, ad_identifier, placement, user_id, session_id, ip_address, target_url, timestamp FROM invoices_adclick')
    rows = cur.fetchall()
    pgcur = pg_conn.cursor()
    for r in rows:
        (id_, ad_identifier, placement, user_id, session_id, ip_address, target_url, timestamp) = r
        pgcur.execute('''
            INSERT INTO ad_clicks(click_id, user_id, session_id, ad_identifier, placement, timestamp, target_url, user_context, invoice_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (click_id) DO UPDATE SET ad_identifier = EXCLUDED.ad_identifier
        ''', (id_, user_id, session_id, ad_identifier, placement, timestamp, target_url, None, None))
    pg_conn.commit()


def set_sequence(pg_conn, table, id_col):
    cur = pg_conn.cursor()
    cur.execute(f"SELECT COALESCE(MAX({id_col}),0) FROM {table}")
    maxid = cur.fetchone()[0] or 0
    seq_name = f"{table}_{id_col}_seq"
    try:
        cur.execute(f"SELECT setval(%s, %s)", (seq_name, maxid))
    except Exception:
        # try to create sequence if not exists
        cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name} START WITH {maxid+1}")
    pg_conn.commit()


def main():
    args = parse_args()
    sqlite_conn = sqlite3.connect(args.sqlite)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = pg_connect(args.postgres)

    print('Copying business profiles...')
    copy_business_profiles(sqlite_conn, pg_conn)
    print('Copying clients...')
    copy_clients(sqlite_conn, pg_conn)
    print('Copying invoices...')
    copy_invoices(sqlite_conn, pg_conn)
    print('Copying invoice items...')
    copy_invoice_items(sqlite_conn, pg_conn)
    print('Copying ad clicks...')
    copy_ad_clicks(sqlite_conn, pg_conn)

    # set sequences
    print('Adjusting sequences...')
    set_sequence(pg_conn, 'clients', 'client_id')
    set_sequence(pg_conn, 'invoices', 'invoice_id')
    set_sequence(pg_conn, 'invoice_items', 'item_id')
    set_sequence(pg_conn, 'ad_clicks', 'click_id')

    print('Done. Verify data in pgAdmin or via Django admin.')


if __name__ == '__main__':
    main()
