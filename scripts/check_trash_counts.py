import os, django, sys
# Ensure project root is on sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
	sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from invoices.models import BusinessProfileTrash, ClientTrash, InvoiceTrash
print('BP trash count:', BusinessProfileTrash.objects.count())
print('Client trash count:', ClientTrash.objects.count())
print('Invoice trash count:', InvoiceTrash.objects.count())
