# Migration to create trash/archive tables for soft-deleted items
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0005_add_soft_delete'),
    ]

    operations = [
        migrations.CreateModel(
            name='BusinessProfileTrash',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('original_id', models.IntegerField(blank=True, null=True)),
                ('business_name', models.CharField(max_length=200)),
                ('logo_name', models.CharField(blank=True, max_length=500)),
                ('address', models.TextField(blank=True)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=100)),
                ('zip_code', models.CharField(blank=True, max_length=20)),
                ('country', models.CharField(blank=True, max_length=100)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=50)),
                ('created_at', models.DateTimeField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
            ],
        ),
        migrations.CreateModel(
            name='ClientTrash',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('original_id', models.IntegerField(blank=True, null=True)),
                ('name', models.CharField(max_length=200)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=50)),
                ('address', models.TextField(blank=True)),
                ('street', models.CharField(blank=True, max_length=200)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=100)),
                ('zip_code', models.CharField(blank=True, max_length=20)),
                ('country', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
            ],
        ),
        migrations.CreateModel(
            name='InvoiceTrash',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('original_id', models.IntegerField(blank=True, null=True)),
                ('client_id', models.IntegerField(blank=True, null=True)),
                ('client_name', models.CharField(blank=True, max_length=200)),
                ('client_email', models.EmailField(blank=True, max_length=254)),
                ('client_phone', models.CharField(blank=True, max_length=50)),
                ('client_address', models.TextField(blank=True)),
                ('business_name', models.CharField(blank=True, max_length=200)),
                ('business_email', models.EmailField(blank=True, max_length=254)),
                ('business_phone', models.CharField(blank=True, max_length=50)),
                ('business_address', models.TextField(blank=True)),
                ('business_logo_name', models.CharField(blank=True, max_length=500)),
                ('invoice_number', models.CharField(max_length=50)),
                ('invoice_date', models.DateField(blank=True, null=True)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(blank=True, max_length=20)),
                ('tax_rate', models.DecimalField(decimal_places=2, default='0.00', max_digits=5)),
                ('discount_amount', models.DecimalField(decimal_places=2, default='0.00', max_digits=10)),
                ('subtotal', models.DecimalField(decimal_places=2, default='0.00', max_digits=12)),
                ('tax_amount', models.DecimalField(decimal_places=2, default='0.00', max_digits=12)),
                ('total_amount', models.DecimalField(decimal_places=2, default='0.00', max_digits=12)),
                ('notes', models.TextField(blank=True)),
                ('payment_terms', models.TextField(blank=True)),
                ('currency', models.CharField(default='USD', max_length=8)),
                ('items', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
            ],
        ),
    ]
