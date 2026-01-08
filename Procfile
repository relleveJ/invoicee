release: python manage.py makemigrations --noinput && python manage.py migrate --noinput && python manage.py collectstatic --noinput
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
