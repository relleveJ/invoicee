import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()

from django.contrib.auth import get_user_model
from invoices.models import BusinessProfile, Client, Invoice, InvoiceItem, BusinessProfileTrash, ClientTrash, InvoiceTrash
from invoices import views
from django.utils import timezone
from datetime import date

User = get_user_model()

print('Starting smoke tests v2...')

# Use existing smoke users if present
user_a = User.objects.filter(username='smoke_user_a').first()
if not user_a:
    user_a = User.objects.create(username='smoke_user_a', email='a@example.com')
    user_a.set_password('testpass'); user_a.save()

# Create minimal invoice for user_a
client = Client.objects.create(user=user_a, name='SMOKE Client V2')
inv = Invoice.objects.create(user=user_a, client=client, client_name=client.name, invoice_number=f'SMOKE-V2-{int(timezone.now().timestamp())}', invoice_date=date.today())
InvoiceItem.objects.create(invoice=inv, description='X', quantity=1, unit_price=5)
inv.recalc_totals()
print('Created invoice', inv.pk)

# Try moving with explicit user argument (should be True)
print('Attempt move with user=object:', views._move_invoice_to_trash(inv.pk, user=user_a))
# If that failed, try with user=None
print('Attempt move with user=None:', views._move_invoice_to_trash(inv.pk, user=None))

print('InvoiceTrash entries for original id:', InvoiceTrash.objects.filter(original_id=inv.pk).count())
print('Done v2')
