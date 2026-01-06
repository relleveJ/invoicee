from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone
import random


class Command(BaseCommand):
    help = 'Create the users_activity_logs table if it does not exist (supports sqlite and postgresql). Use --seed N to insert N sample rows.'

    def add_arguments(self, parser):
        parser.add_argument('--seed', type=int, help='Insert sample rows after creating table')

    def handle(self, *args, **options):
        seed = options.get('seed') or 0
        vendor = connection.vendor
        with connection.cursor() as cursor:
            if vendor == 'postgresql':
                create_sql = '''
                CREATE TABLE IF NOT EXISTS users_activity_logs (
                    activity_id bigserial PRIMARY KEY,
                    user_id integer,
                    activity_type varchar(200),
                    timestamp timestamptz,
                    related_invoice varchar(200)
                );
                '''
                cursor.execute(create_sql)
                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS users_activity_logs_user_id_idx ON users_activity_logs (user_id);")
                except Exception:
                    pass
            else:
                # sqlite and other vendors: use integer PK autoincrement
                create_sql = '''
                CREATE TABLE IF NOT EXISTS users_activity_logs (
                    activity_id integer PRIMARY KEY AUTOINCREMENT,
                    user_id integer,
                    activity_type text,
                    timestamp datetime,
                    related_invoice text
                );
                '''
                cursor.execute(create_sql)
                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS users_activity_logs_user_id_idx ON users_activity_logs (user_id);")
                except Exception:
                    pass

        self.stdout.write(self.style.SUCCESS('Ensured users_activity_logs table exists.'))

        if seed > 0:
            now = timezone.now()
            sample_types = ['invoice_view', 'invoice_create', 'invoice_edit', 'invoice_delete', 'login']
            inserted = 0
            with connection.cursor() as cursor:
                for i in range(seed):
                    uid = random.randint(1, 5)
                    atype = random.choice(sample_types)
                    related = str(random.randint(1, 20)) if 'invoice' in atype else None
                    try:
                        cursor.execute("INSERT INTO users_activity_logs (user_id, activity_type, timestamp, related_invoice) VALUES (%s, %s, %s, %s)", [uid, atype, now, related])
                        inserted += 1
                    except Exception:
                        pass
            self.stdout.write(self.style.SUCCESS(f'Inserted {inserted} sample rows into users_activity_logs'))
