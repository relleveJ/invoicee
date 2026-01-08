#!/bin/sh
set -e

echo "Entry point: checking database and running setup tasks..."

if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -q -E '^postgres'; then
	echo "Detected Postgres DATABASE_URL, waiting for DB to be ready..."
	python - <<'PY'
import os, time, sys
import psycopg2

url = os.environ.get('DATABASE_URL')
deadline = time.time() + 60
while True:
		try:
				conn = psycopg2.connect(url)
				conn.close()
				print('DB is available')
				break
		except Exception as e:
				if time.time() > deadline:
						print('Timed out waiting for DB:', e)
						sys.exit(1)
				print('DB not ready, retrying in 2s...')
				time.sleep(2)
PY
else
	echo "No Postgres DATABASE_URL detected, skipping DB wait."
fi

echo "Running migrations..."
python manage.py makemigrations --noinput || true
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting application..."
exec "$@"
