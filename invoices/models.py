from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


class BusinessProfile(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
	business_name = models.CharField(max_length=200)
	logo = models.ImageField(upload_to='logos/', null=True, blank=True)
	address = models.TextField(blank=True)
	city = models.CharField(max_length=100, blank=True)
	state = models.CharField(max_length=100, blank=True)
	zip_code = models.CharField(max_length=20, blank=True)
	country = models.CharField(max_length=100, blank=True)
	email = models.EmailField(blank=True)
	phone = models.CharField(max_length=50, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	# Soft-delete support
	is_deleted = models.BooleanField(default=False)
	deleted_at = models.DateTimeField(null=True, blank=True)

	def __str__(self):
		return self.business_name


class Client(models.Model):
	# Make user optional so clients can be shared across users
	user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
	name = models.CharField(max_length=200)
	email = models.EmailField(blank=True)
	phone = models.CharField(max_length=50, blank=True)
	# Separate address fields for easier display
	address = models.TextField(blank=True)
	street = models.CharField(max_length=200, blank=True)
	city = models.CharField(max_length=100, blank=True)
	state = models.CharField(max_length=100, blank=True)
	zip_code = models.CharField(max_length=20, blank=True)
	country = models.CharField(max_length=100, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	# Soft-delete support
	is_deleted = models.BooleanField(default=False)
	deleted_at = models.DateTimeField(null=True, blank=True)

	def __str__(self):
		return self.name


class Invoice(models.Model):
	STATUS_CHOICES = [
		('draft', 'Draft'),
		('sent', 'Sent'),
		('paid', 'Paid'),
		('overdue', 'Overdue'),
	]

	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
	client = models.ForeignKey(Client, related_name='invoices', on_delete=models.CASCADE)

	# Snapshot / override fields: allow invoice to store client info at time of issuance
	client_name = models.CharField(max_length=200, blank=True)
	client_email = models.EmailField(blank=True)
	client_phone = models.CharField(max_length=50, blank=True)
	client_address = models.TextField(blank=True)

	# Business snapshot: store business profile information on the invoice so
	# the invoice PDF/preview remains accurate even if the user's BusinessProfile
	# changes later. These fields are optional and populated at save-time.
	business_name = models.CharField(max_length=200, blank=True)
	business_email = models.EmailField(blank=True)
	business_phone = models.CharField(max_length=50, blank=True)
	business_address = models.TextField(blank=True)
	business_logo = models.ImageField(upload_to='invoice_logos/', null=True, blank=True)

	invoice_number = models.CharField(max_length=50, unique=True)
	invoice_date = models.DateField()
	due_date = models.DateField(null=True, blank=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
	tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
	discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
	subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
	tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
	total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
	notes = models.TextField(blank=True)
	payment_terms = models.TextField(blank=True)
	currency = models.CharField(max_length=8, default='USD')
	created_at = models.DateTimeField(auto_now_add=True)

	# Soft-delete support
	is_deleted = models.BooleanField(default=False)
	deleted_at = models.DateTimeField(null=True, blank=True)

	def __str__(self):
		return f"{self.invoice_number} - {self.client}"

	def recalc_totals(self):
		items = self.items.all()
		subtotal = sum((item.line_total for item in items), Decimal('0.00'))
		tax_amount = (subtotal * (self.tax_rate or Decimal('0.00'))) / Decimal('100')
		total = subtotal + tax_amount - (self.discount_amount or Decimal('0.00'))
		self.subtotal = subtotal
		self.tax_amount = tax_amount
		self.total_amount = total
		self.save(update_fields=['subtotal', 'tax_amount', 'total_amount'])


class InvoiceItem(models.Model):
	invoice = models.ForeignKey(Invoice, related_name='items', on_delete=models.CASCADE)
	description = models.TextField(blank=True)
	quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
	unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
	line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

	def __str__(self):
		return f"{self.description} ({self.quantity} x {self.unit_price})"

	def save(self, *args, **kwargs):
		self.line_total = (self.quantity or Decimal('0.00')) * (self.unit_price or Decimal('0.00'))
		super().save(*args, **kwargs)


class AdClick(models.Model):
	ad_identifier = models.CharField(max_length=200)
	placement = models.CharField(max_length=200, blank=True)
	user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
	session_id = models.CharField(max_length=200, blank=True)
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	target_url = models.URLField(blank=True)
	timestamp = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.ad_identifier} @ {self.timestamp}"


class BusinessProfileTrash(models.Model):
	"""Archive table for trashed BusinessProfile records."""
	original_id = models.IntegerField(null=True, blank=True)
	user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
	business_name = models.CharField(max_length=200)
	logo_name = models.CharField(max_length=500, blank=True)
	address = models.TextField(blank=True)
	city = models.CharField(max_length=100, blank=True)
	state = models.CharField(max_length=100, blank=True)
	zip_code = models.CharField(max_length=20, blank=True)
	country = models.CharField(max_length=100, blank=True)
	email = models.EmailField(blank=True)
	phone = models.CharField(max_length=50, blank=True)
	created_at = models.DateTimeField(null=True, blank=True)
	deleted_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"Trashed Business: {self.business_name}"


class ClientTrash(models.Model):
	original_id = models.IntegerField(null=True, blank=True)
	user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
	name = models.CharField(max_length=200)
	email = models.EmailField(blank=True)
	phone = models.CharField(max_length=50, blank=True)
	address = models.TextField(blank=True)
	street = models.CharField(max_length=200, blank=True)
	city = models.CharField(max_length=100, blank=True)
	state = models.CharField(max_length=100, blank=True)
	zip_code = models.CharField(max_length=20, blank=True)
	country = models.CharField(max_length=100, blank=True)
	created_at = models.DateTimeField(null=True, blank=True)
	deleted_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"Trashed Client: {self.name}"


class InvoiceTrash(models.Model):
	original_id = models.IntegerField(null=True, blank=True)
	user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
	client_id = models.IntegerField(null=True, blank=True)
	client_name = models.CharField(max_length=200, blank=True)
	client_email = models.EmailField(blank=True)
	client_phone = models.CharField(max_length=50, blank=True)
	client_address = models.TextField(blank=True)

	business_name = models.CharField(max_length=200, blank=True)
	business_email = models.EmailField(blank=True)
	business_phone = models.CharField(max_length=50, blank=True)
	business_address = models.TextField(blank=True)
	business_logo_name = models.CharField(max_length=500, blank=True)

	invoice_number = models.CharField(max_length=50)
	invoice_date = models.DateField(null=True, blank=True)
	due_date = models.DateField(null=True, blank=True)
	status = models.CharField(max_length=20, blank=True)
	tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
	discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
	subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
	tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
	total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
	notes = models.TextField(blank=True)
	payment_terms = models.TextField(blank=True)
	currency = models.CharField(max_length=8, default='USD')
	items = models.JSONField(null=True, blank=True)
	created_at = models.DateTimeField(null=True, blank=True)
	deleted_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"Trashed Invoice: {self.invoice_number}"


class UsersActivityLog(models.Model):
	"""Unmanaged model mapping to existing PostgreSQL table `users_activity_logs`.
	Columns expected: activity_id, user_id, activity_type, timestamp, related_invoice
	"""
	activity_id = models.BigIntegerField(primary_key=True)
	user_id = models.IntegerField(db_index=True)
	activity_type = models.CharField(max_length=200)
	timestamp = models.DateTimeField()
	related_invoice = models.CharField(max_length=200, null=True, blank=True)

	class Meta:
		db_table = 'users_activity_logs'
		managed = False

	def __str__(self):
		return f"{self.activity_type} by {self.user_id} @ {self.timestamp}"


# Signals to keep invoice totals up to date
@receiver(post_save, sender=InvoiceItem)
def invoiceitem_saved(sender, instance, **kwargs):
	if instance.invoice_id:
		instance.invoice.recalc_totals()


@receiver(post_delete, sender=InvoiceItem)
def invoiceitem_deleted(sender, instance, **kwargs):
	if instance.invoice_id:
		instance.invoice.recalc_totals()

