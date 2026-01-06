import os
import sys

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.contrib.auth import get_user_model
from invoices.models import Client, Invoice, BusinessProfile

def q(msg, qs):
    print(msg)
    for row in qs:
        print(' ', row)

User = get_user_model()

print('Users:')
for u in User.objects.all().order_by('id'):
    print(' ', u.id, u.username, 'is_superuser=' + str(u.is_superuser))

print('\nClient id=4:')
try:
    c = Client.objects.filter(pk=4).values('id','user_id','name','email')
    print(list(c))
except Exception as e:
    print('  error:', e)

print('\nInvoice id=13:')
try:
    i = Invoice.objects.filter(pk=13).values('id','user_id','client_id','invoice_number')
    print(list(i))
except Exception as e:
    print('  error:', e)

print('\nBusinessProfiles:')
try:
    for b in BusinessProfile.objects.all().order_by('id'):
        print(' ', b.id, 'user_id=', getattr(b, 'user_id', None), 'name=', b.business_name)
except Exception as e:
    print('  error:', e)

print('\nCounts:')
from django.db import connection
tables = ['invoices_client','invoices_invoice','invoices_invoiceitem','invoices_businessprofile']
for t in tables:
    try:
        with connection.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "{t}"')
            print(' ', t, cur.fetchone()[0])
    except Exception as e:
        print(' ', t, 'error:', e)

print('\nFinished diagnostics')
