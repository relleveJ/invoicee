#!/usr/bin/env python3
"""
Apply the SQL file `scripts/pg_create_tables.sql` to the given Postgres DATABASE_URL
This avoids requiring the `psql` CLI to be in PATH.

Usage:
  python scripts/apply_pg_create_tables.py "postgresql://user:pass@host:port/dbname"
"""
import sys
import psycopg2


def main():
    if len(sys.argv) < 2:
        print('Usage: apply_pg_create_tables.py <DATABASE_URL>')
        sys.exit(2)
    dsn = sys.argv[1]
    sql_path = 'scripts/pg_create_tables.sql'
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
        print('SQL applied successfully')
    except Exception as e:
        print('Error applying SQL:', e)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
