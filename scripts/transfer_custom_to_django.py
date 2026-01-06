#!/usr/bin/env python3
"""
Detect data in custom tables (e.g., 'invoices') and transfer into Django-managed
tables (e.g., 'invoices_invoice') by mapping common columns where possible.

Usage:
  python scripts/transfer_custom_to_django.py "postgresql://user:pass@host:port/db"

This script is cautious: it will only insert rows when the target Django table
is empty and the source custom table contains data. It prints actions and
uses transactions for safety.
"""

import sys
import psycopg2
from psycopg2 import sql


PAIRS = [
    # (source_table, target_table, mapping dict source->target)
    ('invoices', 'invoices_invoice', {
        'invoice_id': 'id',
        'user_id': 'user_id',
        'client_id': 'client_id',
        'invoice_number': 'invoice_number',
        'invoice_date': 'invoice_date',
        'due_date': 'due_date',
        'status': 'status',
        'subtotal': 'subtotal',
        'tax_rate': 'tax_rate',
        'tax_amount': 'tax_amount',
        'discount_amount': 'discount_amount',
        'total_amount': 'total_amount',
        'currency': 'currency',
        'payment_terms': 'payment_terms',
        'notes': 'notes',
        'created_timestamp': 'created_at'
    }),
    ('clients', 'invoices_client', {
        'client_id': 'id',
        'user_id': 'user_id',
        'client_business_or_person_name': 'name',
        'client_email': 'email',
        'client_phone': 'phone',
        'client_address': 'address',
        'created_date': 'created_at',
        'total_invoices_sent': None, # no direct mapping
        'total_amount_invoiced': None
    }),
    ('invoice_items', 'invoices_invoiceitem', {
        'item_id': 'id',
        'invoice_id': 'invoice_id',
        'item_description': 'description',
        'quantity': 'quantity',
        'unit_price': 'unit_price',
        'line_total': 'line_total',
        'item_order': None
    }),
    ('business_profiles', 'invoices_businessprofile', {
        'user_id': 'id',
        'business_name': 'business_name',
        'business_logo': 'logo',
        'business_address': 'address',
        'street': None,
        'city': 'city',
        'state': 'state',
        'zip': 'zip_code',
        'country': 'country',
        'email': 'email',
        'phone': 'phone',
        'website': None,
        'tax_id': None,
        'created_date': 'created_at',
        'last_login': None
    }),
    ('ad_clicks', 'invoices_adclick', {
        'click_id': 'id',
        'user_id': 'user_id',
        'session_id': 'session_id',
        'ad_identifier': 'ad_identifier',
        'placement': 'placement',
        'timestamp': 'timestamp',
        'target_url': 'target_url',
        'user_context': None,
        'invoice_id': None
    })
]


def connect(dsn):
    return psycopg2.connect(dsn)


def table_exists(cur, table):
    cur.execute("SELECT to_regclass(%s)", (table,))
    return cur.fetchone()[0] is not None


def count_rows(cur, table):
    cur.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table)))
    return cur.fetchone()[0]


def transfer(conn, src, dst, mapping):
    cur = conn.cursor()
    if not table_exists(cur, src):
        print(f"Source table {src} does not exist — skipping")
        return
    if not table_exists(cur, dst):
        print(f"Target table {dst} does not exist — skipping")
        return

    src_count = count_rows(cur, src)
    dst_count = count_rows(cur, dst)
    print(f"{src}: {src_count} rows, {dst}: {dst_count} rows")
    if src_count == 0:
        print(f"No data in {src}; skipping")
        return
    if dst_count > 0:
        print(f"Target {dst} already has rows; skipping to avoid duplicates")
        return

    # Build insert columns: only columns where mapping value is not None and exists in source
    src_cols = []
    dst_cols = []
    for s, d in mapping.items():
        if d is None:
            continue
        src_cols.append(s)
        dst_cols.append(d)

    if not src_cols:
        print(f"No mappable columns for {src} -> {dst}; skipping")
        return

    insert_sql = sql.SQL('INSERT INTO {dst} ({dst_cols}) SELECT {src_cols} FROM {src}').format(
        dst=sql.Identifier(dst),
        dst_cols=sql.SQL(',').join(map(sql.Identifier, dst_cols)),
        src_cols=sql.SQL(',').join(map(sql.Identifier, src_cols)),
        src=sql.Identifier(src)
    )
    print('Executing transfer:', insert_sql.as_string(conn))
    cur.execute('BEGIN')
    try:
        cur.execute(insert_sql)
        cur.execute('COMMIT')
        print(f"Transferred {src_count} rows from {src} to {dst}")
    except Exception as e:
        cur.execute('ROLLBACK')
        print('Transfer failed:', e)


def main():
    if len(sys.argv) < 2:
        print('Usage: transfer_custom_to_django.py <POSTGRES_DSN>')
        sys.exit(2)
    dsn = sys.argv[1]
    conn = connect(dsn)
    for src, dst, mapping in PAIRS:
        transfer(conn, src, dst, mapping)
    conn.close()


if __name__ == '__main__':
    main()
