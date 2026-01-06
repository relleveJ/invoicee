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

print('Starting smoke tests...')

# Create or get users
user_a, _ = User.objects.get_or_create(username='smoke_user_a', defaults={'email':'a@example.com'})
user_b, _ = User.objects.get_or_create(username='smoke_user_b', defaults={'email':'b@example.com'})

# Ensure distinct
for u in (user_a, user_b):
    if not u.has_usable_password():
        u.set_password('testpass')
        u.save()

# Clean up any pre-existing test data
BusinessProfile.objects.filter(user__in=[user_a, user_b], business_name__icontains='SMOKE').delete()
Client.objects.filter(user__in=[user_a, user_b], name__icontains='SMOKE').delete()
Invoice.objects.filter(user__in=[user_a, user_b], invoice_number__icontains='SMOKE').delete()
BusinessProfileTrash.objects.filter(business_name__icontains='SMOKE').delete()
ClientTrash.objects.filter(name__icontains='SMOKE').delete()
InvoiceTrash.objects.filter(invoice_number__icontains='SMOKE').delete()

# Create data for user_a
bp = BusinessProfile.objects.create(user=user_a, business_name='SMOKE BP A', email='a@biz', address='Addr A')
client = Client.objects.create(user=user_a, name='SMOKE Client A', email='clienta@example.com')
inv = Invoice.objects.create(user=user_a, client=client, client_name=client.name, invoice_number=f'SMOKE-{int(timezone.now().timestamp())}', invoice_date=date.today())
InvoiceItem.objects.create(invoice=inv, description='Test item', quantity=1, unit_price=10)
inv.recalc_totals()

print('Created records for user_a:', bp.pk, client.pk, inv.pk)

# Verify user_b cannot see user_a's records
bp_b_count = BusinessProfile.objects.filter(user=user_b, is_deleted=False).count()
client_b_count = Client.objects.filter(user=user_b, is_deleted=False).count()
inv_b_count = Invoice.objects.filter(user=user_b, is_deleted=False).count()
print('Counts visible to user_b (should be 0):', bp_b_count, client_b_count, inv_b_count)

# Move to trash as user_a
ok_bp = views._move_business_to_trash(bp.pk, user=user_a)
ok_client = views._move_client_to_trash(client.pk, user=user_a)
ok_inv = views._move_invoice_to_trash(inv.pk, user=user_a)
print('Move to trash results (bp, client, inv):', ok_bp, ok_client, ok_inv)

# Confirm trash entries exist and are owned by user_a
bp_trash = BusinessProfileTrash.objects.filter(original_id=bp.pk, user=user_a).exists()
client_trash = ClientTrash.objects.filter(original_id=client.pk, user=user_a).exists()
inv_trash = InvoiceTrash.objects.filter(original_id=inv.pk, user=user_a).exists()
print('Trash entries present for user_a (bp, client, inv):', bp_trash, client_trash, inv_trash)

# Attempt moving the same records to trash as user_b (should fail)
res_bp_b = views._move_business_to_trash(bp.pk, user=user_b)
res_client_b = views._move_client_to_trash(client.pk, user=user_b)
res_inv_b = views._move_invoice_to_trash(inv.pk, user=user_b)
print('Attempt move to trash as user_b (should be False):', res_bp_b, res_client_b, res_inv_b)

# Restore invoice from trash
it = InvoiceTrash.objects.filter(original_id=inv.pk, user=user_a).first()
if it:
    restored = views._restore_invoice_from_trash(it.pk)
    print('Restore invoice result:', restored)
else:
    print('Invoice trash row not found for restore')

print('Smoke tests complete.')
