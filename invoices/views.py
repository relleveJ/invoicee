import json
import shutil
import subprocess
import tempfile
import os
import logging
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, Http404
from django.db import IntegrityError
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
import shutil
import subprocess
import tempfile
import os


from .models import BusinessProfile, Client, Invoice, InvoiceItem, AdClick, BusinessProfileTrash, ClientTrash, InvoiceTrash
from django.http import JsonResponse
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator
from decimal import Decimal
from .forms import BusinessProfileForm, ClientForm, InvoiceForm, InvoiceItemFormSet, InvoiceItemForm
from django.forms import inlineformset_factory
from datetime import date
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta
from .models import UsersActivityLog
from django.db import DatabaseError, ProgrammingError
from django.views.decorators.http import require_POST
from django.http import HttpResponseForbidden


def get_invoice_or_404_for_user(pk, user):
	"""Return Invoice by pk if owned by `user` or if `user` is superuser; else raise Http404."""
	# Prefer non-deleted invoices for regular users
	if getattr(user, 'is_superuser', False):
		invoice = get_object_or_404(Invoice, pk=pk)
	else:
		invoice = get_object_or_404(Invoice, pk=pk, is_deleted=False)
	if not getattr(user, 'is_superuser', False) and getattr(invoice, 'user_id', None) != getattr(user, 'id', None):
		raise Http404('No Invoice matches the given query.')
	return invoice


def get_business_or_404_for_user(pk, user):
	"""Return BusinessProfile by pk if visible to `user` or raise Http404.
	Regular users only see non-deleted businesses they own; superusers see all.
	"""
	if getattr(user, 'is_superuser', False):
		bp = get_object_or_404(BusinessProfile, pk=pk)
	else:
		bp = get_object_or_404(BusinessProfile, pk=pk, is_deleted=False)
	if not getattr(user, 'is_superuser', False) and getattr(bp, 'user_id', None) != getattr(user, 'id', None):
		raise Http404('No BusinessProfile matches the given query.')
	return bp


def get_businesses_for_user(user):
    """Return BusinessProfile queryset visible to `user` (superuser sees all)."""
    if getattr(user, 'is_superuser', False):
        return BusinessProfile.objects.filter(is_deleted=False).order_by('-created_at')
    return BusinessProfile.objects.filter(user=user, is_deleted=False).order_by('-created_at')

def login_view(request):
	if request.user.is_authenticated:
		return redirect('dashboard')

	if request.method == 'POST':
		form = AuthenticationForm(request, data=request.POST)
		if form.is_valid():
			user = form.get_user()
			login(request, user)
			messages.success(request, 'Logged in successfully.')
			return redirect('dashboard')
		messages.error(request, 'Invalid username or password.')
	else:
		form = AuthenticationForm(request)
	return render(request, 'registration/login.html', {'form': form})


@login_required
def business_restore(request, trash_pk):
	"""Restore a business from trash and redirect back to the trash list."""
	t = BusinessProfileTrash.objects.filter(pk=trash_pk).first()
	if not t:
		messages.error(request, 'Trashed business not found.')
		return redirect('business_trash_list')
	if not request.user.is_superuser and t.user_id != request.user.id:
		messages.error(request, 'Not authorized to restore this item.')
		return redirect('business_trash_list')
	new_pk = _restore_business_from_trash(trash_pk)
	if new_pk:
		messages.success(request, 'Business restored.')
	else:
		messages.error(request, 'Failed to restore business.')
	return redirect('business_trash_list')
def register_view(request):
	if request.user.is_authenticated:
		return redirect('dashboard')

	if request.method == 'POST':
		form = UserCreationForm(request.POST)
		if form.is_valid():
			user = form.save()
			login(request, user)
			messages.success(request, 'Registration successful. You are now logged in.')
			return redirect('dashboard')
		messages.error(request, 'Please correct the errors below.')
	else:
		form = UserCreationForm()
	return render(request, 'registration/register.html', {'form': form})


def logout_view(request):
	logout(request)
	messages.info(request, 'You have been logged out.')
	return redirect('login')


@login_required
def dashboard_view(request):
	# Determine invoices in scope (superuser sees all)
	if request.user.is_superuser:
		invoices_qs = Invoice.objects.filter(is_deleted=False)
		clients_qs = Client.objects.filter(is_deleted=False)
	else:
		invoices_qs = Invoice.objects.filter(user=request.user, is_deleted=False)
		clients_qs = Client.objects.filter(user=request.user, is_deleted=False)

	totals = invoices_qs.aggregate(total_revenue=Sum('total_amount'))
	total_revenue = totals.get('total_revenue') or Decimal('0.00')
	total_invoices = invoices_qs.count()
	paid_count = invoices_qs.filter(status='paid').count()
	overdue_count = invoices_qs.filter(status='overdue').count()
	pending_count = invoices_qs.exclude(status='paid').count()

	recent_invoices = invoices_qs.order_by('-created_at')[:5]

	# Top clients by invoiced amount
	top_clients = clients_qs.annotate(invoices_count=Count('invoices'), total_invoiced=Sum('invoices__total_amount')).order_by('-total_invoiced')[:5]

	context = {
		'total_revenue': total_revenue,
		'total_invoices': total_invoices,
		'paid_count': paid_count,
		'overdue_count': overdue_count,
		'pending_count': pending_count,
		'recent_invoices': recent_invoices,
		'top_clients': top_clients,
	}
	return render(request, 'dashboard.html', context)


@login_required
def business_profile_setup(request):
	# Support multiple BusinessProfiles per user: list, create, edit, delete
	businesses_qs = get_businesses_for_user(request.user)

	# filtering / search
	q = request.GET.get('q', '').strip()
	if q:
		businesses_qs = businesses_qs.filter(business_name__icontains=q) | businesses_qs.filter(email__icontains=q)

	# Paginate businesses (10 per page) - sanitize incoming page number
	_raw_page = request.GET.get('page')
	try:
		page_number = int(_raw_page) if _raw_page is not None else 1
		if page_number < 1:
			page_number = 1
	except Exception:
		page_number = 1
	paginator = Paginator(businesses_qs, 10)
	businesses_page = paginator.get_page(page_number)

	# Delete flow: simple POST with delete_business_pk from template
	if request.method == 'POST' and request.POST.get('delete_business_pk'):
		try:
			pk = int(request.POST.get('delete_business_pk'))
			# Respect visibility rules (superuser may delete any)
			# perform soft-delete by moving to trash
			moved = _move_business_to_trash(pk, user=request.user)
			if moved:
				messages.success(request, 'Business profile moved to trash.')
			else:
				messages.error(request, 'Failed to delete business profile.')
		except Exception:
			messages.error(request, 'Failed to delete business profile.')
		return redirect('business_profile_setup')

	# Edit or create
	edit_id = request.GET.get('id') or request.POST.get('id')
	instance = None
	if edit_id:
		try:
			instance = get_business_or_404_for_user(int(edit_id), request.user)
		except Exception:
			instance = None

	if request.method == 'POST' and not request.POST.get('delete_business_pk'):
		form = BusinessProfileForm(request.POST, request.FILES, instance=instance)
		if form.is_valid():
			bp = form.save(commit=False)
			# Preserve the owner when editing an existing BusinessProfile.
			if not bp.pk:
				# newly created profile: set owner to current user
				bp.user = request.user
			else:
				# editing existing profile: do not reassign ownership. If for some reason
				# the object lacks a user, default to the current user.
				if not getattr(bp, 'user', None):
					bp.user = request.user
			bp.save()
			messages.success(request, 'Business profile saved.')
			return redirect('business_profile_setup')
		else:
			messages.error(request, 'Please correct the errors below.')
			form_to_render = form
	else:
		form_to_render = BusinessProfileForm(instance=instance)

	# If editing an existing BusinessProfile, provide an absolute logo URL to the template
	business_logo_url = ''
	try:
		if instance and getattr(instance, 'logo', None) and getattr(instance.logo, 'url', None):
			business_logo_url = request.build_absolute_uri(instance.logo.url)
	except Exception:
		business_logo_url = ''

	context = {
		'form': form_to_render,
		'businesses': businesses_page,
		'business_logo_url': business_logo_url,
		'page_obj': businesses_page,
		'paginator': paginator,
		'is_paginated': businesses_page.has_other_pages(),
		'q': q,
		'restored_from_trash': request.GET.get('restored_from_trash'),
		'orig_trash_pk': request.GET.get('orig_trash_pk'),
	}

	return render(request, 'invoices/business_profile_form.html', context)


@login_required
def client_list(request):
	# Superusers see all clients; regular users see only their own
	if request.user.is_superuser:
		clients_qs = Client.objects.filter(is_deleted=False)
	else:
		clients_qs = Client.objects.filter(user=request.user, is_deleted=False)

	# filtering / search
	q = request.GET.get('q', '').strip()
	if q:
		clients_qs = clients_qs.filter(name__icontains=q) | clients_qs.filter(email__icontains=q)

	# Annotate with invoice counts and total invoiced amount
	clients_qs = clients_qs.annotate(
		invoices_count=Count('invoices'),
		total_invoiced=Sum('invoices__total_amount')
	).order_by('-created_at')

	# Paginate clients (10 per page) - sanitize incoming page number
	_raw_page = request.GET.get('page')
	try:
		page_number = int(_raw_page) if _raw_page is not None else 1
		if page_number < 1:
			page_number = 1
	except Exception:
		page_number = 1
	paginator = Paginator(clients_qs, 10)
	# Use get_page for robust handling, but pass a sanitized integer
	clients_page = paginator.get_page(page_number)

	context = {
		'clients': clients_page,
		'q': q,
		'page_obj': clients_page,
		'paginator': paginator,
		'is_paginated': clients_page.has_other_pages(),
	}

	return render(request, 'invoices/client_list.html', context)


@login_required
def client_detail_api(request, pk):
	# Only allow access to client details if the client belongs to the requesting user
	if request.user.is_superuser:
		client = get_object_or_404(Client, pk=pk, is_deleted=False)
	else:
		client = get_object_or_404(Client, pk=pk, user=request.user, is_deleted=False)
	data = {
		'id': client.pk,
		'name': client.name,
		'email': client.email,
		'phone': client.phone,
		'street': client.street,
		'city': client.city,
		'state': client.state,
		'zip_code': client.zip_code,
		'country': client.country,
		'address': client.address,
	}
	return JsonResponse(data)


@login_required
def business_detail_api(request, pk):
	bp = get_business_or_404_for_user(pk, request.user)
	data = {
		'id': bp.pk,
		'business_name': bp.business_name,
		'email': bp.email,
		'phone': bp.phone,
		'address': bp.address,
		'city': bp.city,
		'state': bp.state,
		'zip_code': bp.zip_code,
		'country': bp.country,
		'logo_url': bp.logo.url if bp.logo else '',
	}
	return JsonResponse(data)


@login_required
def client_create(request):
	if request.method == 'POST':
		form = ClientForm(request.POST)
		if form.is_valid():
			client = form.save(commit=False)
			client.user = request.user
			client.save()
			messages.success(request, 'Client created.')
			return redirect('client_list')
	else:
		form = ClientForm()
	return render(request, 'invoices/client_form.html', {'form': form, 'action': 'Create'})


@login_required
def client_edit(request, pk):
	client = get_object_or_404(Client, pk=pk, user=request.user, is_deleted=False)
	if request.method == 'POST':
		form = ClientForm(request.POST, instance=client)
		if form.is_valid():
			form.save()
			messages.success(request, 'Client updated.')
			return redirect('client_list')
	else:
		form = ClientForm(instance=client)
	return render(request, 'invoices/client_form.html', {'form': form, 'action': 'Edit'})


@login_required
def client_delete(request, pk):
	client = get_object_or_404(Client, pk=pk, user=request.user, is_deleted=False)
	if request.method == 'POST':
		# perform soft-delete by moving to ClientTrash
		moved = _move_client_to_trash(pk, user=request.user)
		if moved:
			messages.success(request, 'Client moved to trash.')
		else:
			messages.error(request, 'Failed to move client to trash.')
		return redirect('client_list')
	return render(request, 'invoices/client_confirm_delete.html', {'client': client})


@login_required
def business_cancel_restore(request, business_pk):
	"""Move a recently-restored BusinessProfile back to trash (undo restore).
	This is a convenience used by the Cancel button after Restore & Edit.
	"""
	try:
		# respect ownership
		if not request.user.is_superuser:
			bp = BusinessProfile.objects.get(pk=business_pk, user=request.user)
		else:
			bp = BusinessProfile.objects.get(pk=business_pk)
	except BusinessProfile.DoesNotExist:
		messages.error(request, 'Business profile not found or not authorized.')
		return redirect('business_trash_list')
	try:
		moved = _move_business_to_trash(business_pk, user=request.user)
		if moved:
			messages.success(request, 'Restore cancelled; business moved back to trash.')
		else:
			messages.error(request, 'Could not move business back to trash.')
	except Exception:
		logging.exception('Failed cancelling restore for business %s', business_pk)
		messages.error(request, 'Failed cancelling restore.')
	return redirect('business_trash_list')


@login_required
def invoice_list(request):
	# base queryset
	user_param = request.GET.get('user', '').strip()
	show_all = request.GET.get('all', '') == '1'
	if request.user.is_superuser:
		# Superadmin: default to their own invoices unless `user` or `all=1` is provided
		if show_all:
			invoices_qs = Invoice.objects.filter(is_deleted=False)
		elif user_param:
			try:
				invoices_qs = Invoice.objects.filter(user_id=int(user_param), is_deleted=False)
			except Exception:
				invoices_qs = Invoice.objects.filter(user=request.user, is_deleted=False)
		else:
			invoices_qs = Invoice.objects.filter(user=request.user, is_deleted=False)
	else:
		invoices_qs = Invoice.objects.filter(user=request.user, is_deleted=False)

	# search and status filtering
	q = request.GET.get('q', '').strip()
	status = request.GET.get('status', '').strip()
	if q:
		invoices_qs = invoices_qs.filter(invoice_number__icontains=q) | invoices_qs.filter(client__name__icontains=q)
	if status:
		invoices_qs = invoices_qs.filter(status=status)

	invoices = invoices_qs.order_by('-created_at')
	return render(request, 'invoices/invoice_list.html', {'invoices': invoices, 'q': q, 'status': status, 'user_param': user_param, 'show_all': show_all})


@login_required
def _bulk_update_delete(model_cls, pks, action, user=None):
	"""Helper to perform bulk actions on model instances.
	action: 'trash', 'restore', 'delete'"""
	objs = model_cls.objects.filter(pk__in=pks)
	# Respect ownership when possible
	if user and not getattr(user, 'is_superuser', False):
		# filter by user attribute when present
		if hasattr(model_cls, 'user'):
			objs = objs.filter(user=user)
	# Deprecated generic updater. Keep for compatibility but prefer model-specific trash handlers.
	return 0


def _move_business_to_trash(pk, user=None):
	try:
		# Respect ownership: if a user is provided and is not superuser, enforce it
		if user and not getattr(user, 'is_superuser', False):
			b = BusinessProfile.objects.get(pk=pk, user=user)
		else:
			b = BusinessProfile.objects.get(pk=pk)
	except BusinessProfile.DoesNotExist:
		return False
	try:
		BusinessProfileTrash.objects.create(
			original_id=b.pk,
			user=(user if user is not None else b.user),
			business_name=b.business_name,
			logo_name=(b.logo.name if getattr(b, 'logo', None) else ''),
			address=b.address,
			city=b.city,
			state=b.state,
			zip_code=b.zip_code,
			country=b.country,
			email=b.email,
			phone=b.phone,
			created_at=getattr(b, 'created_at', None),
		)
		# soft-delete original
		b.is_deleted = True
		b.deleted_at = timezone.now()
		b.save(update_fields=['is_deleted', 'deleted_at'])
		return True
	except Exception:
		logging.exception('Failed to move BusinessProfile %s to trash', pk)
		return False


def _restore_business_from_trash(trash_pk):
	try:
		t = BusinessProfileTrash.objects.get(pk=trash_pk)
	except BusinessProfileTrash.DoesNotExist:
		return False
	try:
		# If original exists, restore it; otherwise create a new one
		if t.original_id:
			bp = BusinessProfile.objects.filter(pk=t.original_id).first()
		else:
			bp = None
		if bp:
			bp.business_name = t.business_name
			bp.address = t.address
			bp.city = t.city
			bp.state = t.state
			bp.zip_code = t.zip_code
			bp.country = t.country
			bp.email = t.email
			bp.phone = t.phone
			if t.logo_name:
				try:
					bp.logo.name = t.logo_name
				except Exception:
					pass
			bp.is_deleted = False
			bp.deleted_at = None
			bp.save()
			t.delete()
			return bp.pk
		else:
			bp = BusinessProfile(
				user=t.user,
				business_name=t.business_name,
				address=t.address,
				city=t.city,
				state=t.state,
				zip_code=t.zip_code,
				country=t.country,
				email=t.email,
				phone=t.phone,
			)
			if t.logo_name:
				try:
					bp.logo.name = t.logo_name
				except Exception:
					pass
			bp.save()
			t.delete()
			return bp.pk
	except Exception:
		logging.exception('Failed to restore BusinessProfile from trash %s', trash_pk)
		return False


def _move_client_to_trash(pk, user=None):
	try:
		# Clients may be shared (user nullable). Enforce ownership when a user is provided.
		if user and not getattr(user, 'is_superuser', False):
			c = Client.objects.get(pk=pk, user=user)
		else:
			c = Client.objects.get(pk=pk)
	except Client.DoesNotExist:
		return False
	try:
		ClientTrash.objects.create(
			original_id=c.pk,
			user=(user if user is not None else c.user),
			name=c.name,
			email=c.email,
			phone=c.phone,
			address=c.address,
			street=c.street,
			city=c.city,
			state=c.state,
			zip_code=c.zip_code,
			country=c.country,
			created_at=getattr(c, 'created_at', None),
		)
		# soft-delete original client
		c.is_deleted = True
		c.deleted_at = timezone.now()
		c.save(update_fields=['is_deleted', 'deleted_at'])
		return True
	except Exception:
		logging.exception('Failed to move Client %s to trash', pk)
		return False


def _restore_client_from_trash(trash_pk):
	try:
		t = ClientTrash.objects.get(pk=trash_pk)
	except ClientTrash.DoesNotExist:
		return False
	try:
		# If original exists, restore it
		if t.original_id:
			c = Client.objects.filter(pk=t.original_id).first()
		else:
			c = None
		if c:
			c.name = t.name
			c.email = t.email
			c.phone = t.phone
			c.address = t.address
			c.street = t.street
			c.city = t.city
			c.state = t.state
			c.zip_code = t.zip_code
			c.country = t.country
			c.is_deleted = False
			c.deleted_at = None
			c.save()
			t.delete()
			return c.pk
		else:
			c = Client(
				user=t.user,
				name=t.name,
				email=t.email,
				phone=t.phone,
				address=t.address,
				street=t.street,
				city=t.city,
				state=t.state,
				zip_code=t.zip_code,
				country=t.country,
			)
			c.save()
			t.delete()
			return c.pk
	except Exception:
		logging.exception('Failed to restore Client from trash %s', trash_pk)
		return False


def _move_invoice_to_trash(pk, user=None):
	try:
		# Enforce ownership: only allow moving invoices owned by the requesting user
		if user and not getattr(user, 'is_superuser', False):
			inv = Invoice.objects.get(pk=pk, user=user)
		else:
			inv = Invoice.objects.get(pk=pk)
	except Invoice.DoesNotExist:
		return False
	try:
		# Serialize items into JSON-safe Python types (convert Decimals to floats)
		raw_items = list(inv.items.values('description', 'quantity', 'unit_price', 'line_total'))
		items = []
		for it in raw_items:
			items.append({
				'description': it.get('description', '') or '',
				'quantity': float(it.get('quantity') or 0),
				'unit_price': float(it.get('unit_price') or 0),
				'line_total': float(it.get('line_total') or 0),
			})
		# items serialized into JSON-safe Python types
		payload = dict(
			original_id=inv.pk,
			user=(user if user is not None else inv.user),
			client_id=(inv.client.pk if getattr(inv, 'client', None) else None),
			client_name=inv.client_name,
			client_email=inv.client_email,
			client_phone=inv.client_phone,
			client_address=inv.client_address,
			business_name=inv.business_name,
			business_email=inv.business_email,
			business_phone=inv.business_phone,
			business_address=inv.business_address,
			business_logo_name=(inv.business_logo.name if getattr(inv, 'business_logo', None) else ''),
			invoice_number=inv.invoice_number,
			invoice_date=inv.invoice_date,
			due_date=inv.due_date,
			status=inv.status,
			tax_rate=inv.tax_rate,
			discount_amount=inv.discount_amount,
			subtotal=inv.subtotal,
			tax_amount=inv.tax_amount,
			total_amount=inv.total_amount,
			notes=inv.notes,
			payment_terms=inv.payment_terms,
			currency=inv.currency,
			items=items,
			created_at=getattr(inv, 'created_at', None),
		)
		# payload prepared for creation
		# Ensure idempotency: if an InvoiceTrash already exists for this original_id,
		# update it instead of creating a duplicate. This prevents duplicate archive
		# rows when the helper is called multiple times (e.g., bulk + per-item flows).
		existing = None
		try:
			existing = InvoiceTrash.objects.filter(original_id=inv.pk).first()
		except Exception:
			existing = None
		if existing:
			# update existing archive record fields
			try:
				existing.user = payload.get('user')
				existing.client_id = payload.get('client_id')
				existing.client_name = payload.get('client_name')
				existing.client_email = payload.get('client_email')
				existing.client_phone = payload.get('client_phone')
				existing.client_address = payload.get('client_address')
				existing.business_name = payload.get('business_name')
				existing.business_email = payload.get('business_email')
				existing.business_phone = payload.get('business_phone')
				existing.business_address = payload.get('business_address')
				existing.business_logo_name = payload.get('business_logo_name') or ''
				existing.invoice_number = payload.get('invoice_number')
				existing.invoice_date = payload.get('invoice_date')
				existing.due_date = payload.get('due_date')
				existing.status = payload.get('status')
				existing.tax_rate = payload.get('tax_rate')
				existing.discount_amount = payload.get('discount_amount')
				existing.subtotal = payload.get('subtotal')
				existing.tax_amount = payload.get('tax_amount')
				existing.total_amount = payload.get('total_amount')
				existing.notes = payload.get('notes')
				existing.payment_terms = payload.get('payment_terms')
				existing.currency = payload.get('currency')
				existing.items = payload.get('items')
				existing.created_at = payload.get('created_at')
				existing.save()
			except Exception:
				logging.exception('Failed to update existing InvoiceTrash for original_id %s', inv.pk)
		else:
			InvoiceTrash.objects.create(**payload)
		# soft-delete original invoice rather than hard-delete
		inv.is_deleted = True
		inv.deleted_at = timezone.now()
		inv.save(update_fields=['is_deleted', 'deleted_at'])
		return True
	except Exception as e:
		logging.exception('Failed to move Invoice %s to trash', pk)
		# exception logged above
		return False


def _restore_invoice_from_trash(trash_pk):
	try:
		t = InvoiceTrash.objects.get(pk=trash_pk)
	except InvoiceTrash.DoesNotExist:
		return False
	try:
		# If original invoice exists (soft-deleted), restore it
		inv = None
		if t.original_id:
			inv = Invoice.objects.filter(pk=t.original_id).first()
		if inv:
			inv.client = (Client.objects.filter(pk=t.client_id).first() if t.client_id else None)
			inv.client_name = t.client_name
			inv.client_email = t.client_email
			inv.client_phone = t.client_phone
			inv.client_address = t.client_address
			inv.business_name = t.business_name
			inv.business_email = t.business_email
			inv.business_phone = t.business_phone
			inv.business_address = t.business_address
			inv.invoice_number = t.invoice_number
			inv.invoice_date = t.invoice_date
			inv.due_date = t.due_date
			inv.status = t.status or 'draft'
			inv.tax_rate = t.tax_rate
			inv.discount_amount = t.discount_amount
			inv.subtotal = t.subtotal
			inv.tax_amount = t.tax_amount
			inv.total_amount = t.total_amount
			inv.notes = t.notes
			inv.payment_terms = t.payment_terms
			inv.currency = t.currency
			if t.business_logo_name:
				try:
					inv.business_logo.name = t.business_logo_name
				except Exception:
					pass
			inv.is_deleted = False
			inv.deleted_at = None
			inv.save()
			# items likely already exist on soft-deleted invoice; if not, recreate from snapshot
			existing_items = inv.items.count()
			if existing_items == 0 and t.items:
				for it in t.items:
					InvoiceItem.objects.create(
						invoice=inv,
						description=it.get('description',''),
						quantity=it.get('quantity') or 0,
						unit_price=it.get('unit_price') or 0,
						line_total=it.get('line_total') or 0,
					)
				inv.recalc_totals()
			t.delete()
			return inv.pk
		else:
			inv = Invoice(
				user=t.user,
				client=(Client.objects.filter(pk=t.client_id).first() if t.client_id else None),
				client_name=t.client_name,
				client_email=t.client_email,
				client_phone=t.client_phone,
				client_address=t.client_address,
				business_name=t.business_name,
				business_email=t.business_email,
				business_phone=t.business_phone,
				business_address=t.business_address,
				invoice_number=t.invoice_number,
				invoice_date=t.invoice_date,
				due_date=t.due_date,
				status=t.status or 'draft',
				tax_rate=t.tax_rate,
				discount_amount=t.discount_amount,
				subtotal=t.subtotal,
				tax_amount=t.tax_amount,
				total_amount=t.total_amount,
				notes=t.notes,
				payment_terms=t.payment_terms,
				currency=t.currency,
			)
			if t.business_logo_name:
				try:
					inv.business_logo.name = t.business_logo_name
				except Exception:
					pass
			inv.save()
			# restore items
			if t.items:
				for it in t.items:
					InvoiceItem.objects.create(
						invoice=inv,
						description=it.get('description',''),
						quantity=it.get('quantity') or 0,
						unit_price=it.get('unit_price') or 0,
						line_total=it.get('line_total') or 0,
					)
				inv.recalc_totals()
			t.delete()
			return inv.pk
	except Exception:
		logging.exception('Failed to restore Invoice from trash %s', trash_pk)
		return False


@login_required
def business_bulk_action(request):
	if request.method != 'POST':
		return redirect('business_profile_setup')
	pks = request.POST.getlist('selected_ids')
	action = request.POST.get('action') or 'trash'
	if not pks:
		messages.error(request, 'No items selected.')
		return redirect('business_profile_setup')
	try:
		cnt = 0
		if action == 'trash':
			for pk in pks:
				if _move_business_to_trash(pk, user=request.user): cnt += 1
			messages.success(request, f'Moved {cnt} business profile(s) to trash.')
		elif action == 'restore':
			for pk in pks:
				if _restore_business_from_trash(pk): cnt += 1
			messages.success(request, f'Restored {cnt} business profile(s).')
		elif action == 'delete':
			# permanently delete from trash
			for pk in pks:
				try:
					BusinessProfileTrash.objects.filter(pk=pk).delete(); cnt += 1
				except Exception:
					pass
			messages.success(request, f'Deleted {cnt} business profile(s) permanently.')
	except Exception:
		messages.error(request, 'Failed to perform requested action.')
	return redirect('business_profile_setup')


@login_required
def business_trash_list(request):
	# show trashed businesses for the user with search and pagination
	if request.user.is_superuser:
		qs = BusinessProfileTrash.objects.all().order_by('-deleted_at')
	else:
		qs = BusinessProfileTrash.objects.filter(user=request.user).order_by('-deleted_at')
	q = request.GET.get('q', '').strip()
	if q:
		qs = qs.filter(business_name__icontains=q) | qs.filter(email__icontains=q)

	# paginate
	_raw_page = request.GET.get('page')
	try:
		page_number = int(_raw_page) if _raw_page is not None else 1
		if page_number < 1:
			page_number = 1
	except Exception:
		page_number = 1
	paginator = Paginator(qs, 10)
	page = paginator.get_page(page_number)
	context = {
		'businesses': page,
		'q': q,
		'page_obj': page,
		'paginator': paginator,
		'is_paginated': page.has_other_pages(),
	}
	return render(request, 'invoices/business_profile_trash.html', context)


@login_required
def business_restore_and_edit(request, trash_pk):
	"""Restore a BusinessProfile from trash then redirect to edit view."""
	if not request.user.is_authenticated:
		return redirect('login')
	# Only allow owners (or superusers) to restore
	t = BusinessProfileTrash.objects.filter(pk=trash_pk).first()
	if not t:
		messages.error(request, 'Trashed business not found.')
		return redirect('business_trash_list')

	if not request.user.is_superuser and t.user_id != request.user.id:
		messages.error(request, 'Not authorized to restore this item.')
		return redirect('business_trash_list')
	new_pk = _restore_business_from_trash(trash_pk)
	if new_pk:
		# Mark that this was restored from trash so the form can offer a cancel-back option
		return redirect(f"{reverse('business_profile_setup')}?id={new_pk}&restored_from_trash=1&orig_trash_pk={trash_pk}")
	messages.error(request, 'Failed to restore business profile.')
	return redirect('business_trash_list')


@login_required
def client_bulk_action(request):
	if request.method != 'POST':
		return redirect('client_list')
	pks = request.POST.getlist('selected_ids')
	action = request.POST.get('action') or 'trash'
	if not pks:
		messages.error(request, 'No items selected.')
		return redirect('client_list')
	try:
		cnt = 0
		if action == 'trash':
			for pk in pks:
				if _move_client_to_trash(pk, user=request.user): cnt += 1
			messages.success(request, f'Moved {cnt} client(s) to trash.')
		elif action == 'restore':
			for pk in pks:
				if _restore_client_from_trash(pk): cnt += 1
			messages.success(request, f'Restored {cnt} client(s).')
		elif action == 'delete':
			for pk in pks:
				try:
					ClientTrash.objects.filter(pk=pk).delete(); cnt += 1
				except Exception:
					pass
			messages.success(request, f'Deleted {cnt} client(s) permanently.')
	except Exception:
		messages.error(request, 'Failed to perform requested action.')
	return redirect('client_list')


@login_required
def client_trash_list(request):
	# show trashed clients with search and pagination
	if request.user.is_superuser:
		qs = ClientTrash.objects.all().order_by('-deleted_at')
	else:
		qs = ClientTrash.objects.filter(user=request.user).order_by('-deleted_at')
	q = request.GET.get('q', '').strip()
	if q:
		qs = qs.filter(name__icontains=q) | qs.filter(email__icontains=q) | qs.filter(city__icontains=q)

	_raw_page = request.GET.get('page')
	try:
		page_number = int(_raw_page) if _raw_page is not None else 1
		if page_number < 1:
			page_number = 1
	except Exception:
		page_number = 1
	paginator = Paginator(qs, 10)
	page = paginator.get_page(page_number)
	context = {
		'clients': page,
		'q': q,
		'page_obj': page,
		'paginator': paginator,
		'is_paginated': page.has_other_pages(),
	}
	return render(request, 'invoices/client_trash.html', context)


@login_required
def invoice_bulk_action(request):
	if request.method != 'POST':
		return redirect('invoice_list')
	pks = request.POST.getlist('selected_ids')
	action = request.POST.get('action') or 'trash'
	if not pks:
		messages.error(request, 'No items selected.')
		return redirect('invoice_list')
	try:
		cnt = 0
		if action == 'trash':
			for pk in pks:
				if _move_invoice_to_trash(pk, user=request.user): cnt += 1
			messages.success(request, f'Moved {cnt} invoice(s) to trash.')
		elif action == 'restore':
			for pk in pks:
				if _restore_invoice_from_trash(pk): cnt += 1
			messages.success(request, f'Restored {cnt} invoice(s).')
		elif action == 'delete':
			for pk in pks:
				try:
					InvoiceTrash.objects.filter(pk=pk).delete(); cnt += 1
				except Exception:
					pass
			messages.success(request, f'Deleted {cnt} invoice(s) permanently.')
	except Exception:
		messages.error(request, 'Failed to perform requested action.')
	return redirect('invoice_list')


@login_required
def invoice_trash_list(request):
	# show trashed invoices from the InvoiceTrash archive table with search and pagination
	if request.user.is_superuser:
		qs = InvoiceTrash.objects.all().order_by('-deleted_at')
	else:
		qs = InvoiceTrash.objects.filter(user=request.user).order_by('-deleted_at')
	q = request.GET.get('q', '').strip()
	if q:
		qs = qs.filter(invoice_number__icontains=q) | qs.filter(client_name__icontains=q)

	_raw_page = request.GET.get('page')
	try:
		page_number = int(_raw_page) if _raw_page is not None else 1
		if page_number < 1:
			page_number = 1
	except Exception:
		page_number = 1
	paginator = Paginator(qs, 10)
	page = paginator.get_page(page_number)
	context = {
		'invoices': page,
		'q': q,
		'page_obj': page,
		'paginator': paginator,
		'is_paginated': page.has_other_pages(),
	}
	return render(request, 'invoices/invoice_trash.html', context)


@login_required
def invoice_trash_view(request, trash_pk):
	"""Render a read-only view of a trashed invoice from the archive table."""
	t = get_object_or_404(InvoiceTrash, pk=trash_pk)
	# Ensure ownership
	if not request.user.is_superuser and getattr(t, 'user_id', None) != getattr(request.user, 'id', None):
		raise Http404('Not found')
	from types import SimpleNamespace
	invoice = SimpleNamespace(
		pk=t.original_id,
		invoice_number=t.invoice_number,
		invoice_date=t.invoice_date,
		due_date=t.due_date,
		status=t.status,
		tax_rate=t.tax_rate,
		discount_amount=t.discount_amount,
		subtotal=t.subtotal,
		tax_amount=t.tax_amount,
		total_amount=t.total_amount,
		notes=t.notes,
		payment_terms=t.payment_terms,
		currency=t.currency,
		client_name=t.client_name,
		client_email=t.client_email,
		client_phone=t.client_phone,
		client_address=t.client_address,
		business_name=t.business_name,
		business_email=t.business_email,
		business_phone=t.business_phone,
		business_address=t.business_address,
		business_logo=None,
		items=t.items or [],
	)
	# build business simple namespace for template
	business = None
	if t.business_logo_name:
		try:
			from types import SimpleNamespace as SN
			business = SN(business_name=t.business_name, email=t.business_email, phone=t.business_phone, address=t.business_address, logo=SN(url=request.build_absolute_uri('/media/' + t.business_logo_name)))
		except Exception:
			business = None
	return render(request, 'invoices/invoice_detail.html', {'invoice': invoice, 'business': business, 'back_to_trash': True})


@login_required
@xframe_options_exempt
def invoice_live_preview(request):
	"""Accept JSON POST with invoice and items and return PDF (if WeasyPrint native libs available) or HTML preview."""
	if request.method != 'POST':
		return JsonResponse({'error': 'POST required'}, status=405)

	data = None
	# Accept JSON requests (primary) or form-encoded POSTs (fallback from hidden form submit)
	ct = (request.content_type or '').lower()
	if 'application/json' in ct:
		try:
			data = json.loads(request.body.decode('utf-8'))
		except Exception:
			return JsonResponse({'error': 'Invalid JSON'}, status=400)
	else:
		# build a simple data dict from form-encoded POST fields; supports common field names
		try:
			pdata = request.POST
			data = {
				'invoice_number': pdata.get('invoice_number') or pdata.get('id_invoice_number'),
				'invoice_date': pdata.get('invoice_date') or pdata.get('id_invoice_date'),
				'due_date': pdata.get('due_date') or pdata.get('id_due_date'),
				'tax_rate': pdata.get('tax_rate') or pdata.get('id_tax_rate'),
				'discount_amount': pdata.get('discount_amount') or pdata.get('id_discount_amount'),
				'status': pdata.get('status') or pdata.get('id_status'),
				'payment_terms': pdata.get('payment_terms') or pdata.get('id_payment_terms'),
				'notes': pdata.get('notes') or pdata.get('id_notes'),
				'currency': pdata.get('currency') or pdata.get('id_currency') or 'USD',
				'client': {
					'name': pdata.get('client_name') or pdata.get('id_client_name') or pdata.get('client') or '',
					'email': pdata.get('client_email') or pdata.get('id_client_email') or '',
					'phone': pdata.get('client_phone') or pdata.get('id_client_phone') or '',
					'address': pdata.get('client_address') or pdata.get('id_client_address') or '',
				},
				'business': {
					'id': pdata.get('business') or pdata.get('business_id') or '',
					'business_name': pdata.get('business_name') or pdata.get('id_business_name') or pdata.get('business_name') or pdata.get('id_business_name_text') or '',
					'email': pdata.get('business_email') or pdata.get('id_business_email') or pdata.get('id_business_email_text') or '',
					'phone': pdata.get('business_phone') or pdata.get('id_business_phone') or pdata.get('id_business_phone_text') or '',
					'address': pdata.get('business_address') or pdata.get('id_business_address') or pdata.get('id_business_address_text') or '',
					'photo_data_url': pdata.get('business_photo_data_url') or None,
				},
				'items': []
			}
			# attempt to collect formset-like items (e.g., form-0-description or items-0-description)
			import re
			item_map = {}
			for k in pdata.keys():
				m = re.match(r'.*-(\d+)-(.+)', k)
				if m:
					idx = int(m.group(1))
					field = m.group(2)
					item_map.setdefault(idx, {})[field] = pdata.get(k)
			# also handle names like description-0 or 0-description
			for k in pdata.keys():
				m2 = re.match(r'(?:description|desc|item_description)[-_]?(\d+)', k)
				if m2:
					idx = int(m2.group(1))
					item_map.setdefault(idx, {})['description'] = pdata.get(k)
			# convert to list
			for idx in sorted(item_map.keys()):
				itm = item_map[idx]
				try:
					qty = float(itm.get('quantity') or itm.get('qty') or 0)
				except Exception:
					qty = 0
				try:
					unit = float(itm.get('unit_price') or itm.get('price') or 0)
				except Exception:
					unit = 0
				data['items'].append({'description': itm.get('description') or itm.get('desc') or '', 'quantity': qty, 'unit_price': unit})
		except Exception:
			data = {}

	# Build lightweight objects for template rendering
	from types import SimpleNamespace

	client_data = data.get('client') or {}
	client_obj = SimpleNamespace(
		name=client_data.get('name') or client_data.get('display') or 'Client',
		email=client_data.get('email', ''),
		phone=client_data.get('phone', ''),
		address=client_data.get('address', '')
	)

	items = []
	for it in data.get('items', []):
		items.append(SimpleNamespace(description=it.get('description', ''), quantity=it.get('quantity', 0), unit_price=it.get('unit_price', 0), line_total=(float(it.get('quantity', 0)) * float(it.get('unit_price', 0)))))

	class ItemList:
		def __init__(self, items):
			self._items = items
		def all(self):
			return self._items
		def exists(self):
			return bool(self._items)

	subtotal = sum([i.line_total for i in items])
	tax_rate = float(data.get('tax_rate') or 0)
	tax_amount = subtotal * (tax_rate / 100.0)
	discount = float(data.get('discount_amount') or 0)
	total = subtotal + tax_amount - discount

	invoice_obj = SimpleNamespace(
		invoice_number=data.get('invoice_number', 'PREVIEW'),
		invoice_date=data.get('invoice_date', ''),
		due_date=data.get('due_date', ''),
		status=data.get('status', 'draft'),
		# For Django templates that expect a model-like API (invoice.get_status_display),
		# provide a simple attribute so templates can render the status label when
		# previewing via JSON payloads. Capitalize the first letter for readability.
		get_status_display=str(data.get('status', 'draft') or '').capitalize(),
		client=client_obj,
		client_name=client_data.get('name') or None,
		client_email=client_data.get('email') or None,
		client_phone=client_data.get('phone') or None,
		client_address=client_data.get('address') or None,
		items=ItemList(items),
		subtotal=subtotal,
		tax_rate=tax_rate,
		tax_amount=tax_amount,
		discount_amount=discount,
		total_amount=total,
		currency=data.get('currency', 'USD'),
		payment_terms=data.get('payment_terms', ''),
		notes=data.get('notes', ''),
	)

	# If client posted business snapshot data (editable fields or uploaded image), prefer that
	bdata = data.get('business') or {}
	if bdata:
		from types import SimpleNamespace
		biz_logo = None
		# If client posted an uploaded image (data URL), use it
		if bdata.get('photo_data_url'):
			biz_logo = SimpleNamespace(url=bdata.get('photo_data_url'))
		# If no uploaded photo but a business id was provided, try to load stored logo
		elif bdata.get('id'):
			try:
				bp_id = int(bdata.get('id'))
				# Respect superuser visibility when resolving posted business id
				try:
					bp_obj = get_business_or_404_for_user(bp_id, request.user)
				except Exception:
					bp_obj = None
				if bp_obj and getattr(bp_obj, 'logo', None):
					u = bp_obj.logo.url
					if u and not u.startswith('data:') and not u.startswith('http'):
						u = request.build_absolute_uri(u)
					biz_logo = SimpleNamespace(url=u)
			except Exception:
				biz_logo = None
		business = SimpleNamespace(
			business_name=bdata.get('business_name') or bdata.get('name') or '',
			email=bdata.get('email') or '',
			phone=bdata.get('phone') or '',
			address=bdata.get('address') or '',
			city=bdata.get('city') or '',
			state=bdata.get('state') or '',
			zip_code=bdata.get('zip_code') or '',
			country=bdata.get('country') or '',
			logo=biz_logo,
		)
	else:
		# If no posted business snapshot, prefer the first BusinessProfile visible to this user
		bp = get_businesses_for_user(request.user).first()
		if bp:
			# Build a lightweight object so templates can access .logo.url
			from types import SimpleNamespace as _SN
			biz_logo = None
			try:
				if bp.logo:
					# ensure an absolute URL so iframe/srcdoc previews can load the image
					u = bp.logo.url
					if u and not u.startswith('data:') and not u.startswith('http'):
						u = request.build_absolute_uri(u)
					biz_logo = _SN(url=u)
			except Exception:
				biz_logo = None
			business = _SN(
				business_name=getattr(bp, 'business_name', ''),
				email=getattr(bp, 'email', ''),
				phone=getattr(bp, 'phone', ''),
				address=getattr(bp, 'address', ''),
				city=getattr(bp, 'city', ''),
				state=getattr(bp, 'state', ''),
				zip_code=getattr(bp, 'zip_code', ''),
				country=getattr(bp, 'country', ''),
				logo=biz_logo,
			)
		else:
			business = None

	html_string = render_to_string('invoices/invoice_pdf.html', {'invoice': invoice_obj, 'business': business}, request=request)

	# Try to render PDF
	try:
		from weasyprint import HTML
	except Exception:
		# If a PDF download was explicitly requested, still return the HTML but include a helpful status/message.
		# The client-side will handle non-PDF responses gracefully.
		return HttpResponse(html_string, content_type='text/html')

	try:
		html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
		pdf = html.write_pdf()
		response = HttpResponse(pdf, content_type='application/pdf')
		# If client requested a direct download (e.g., ?format=pdf) send as attachment, otherwise inline preview
		if request.GET.get('format') == 'pdf':
			response['Content-Disposition'] = 'attachment; filename="invoice_preview.pdf"'
		else:
			response['Content-Disposition'] = 'inline; filename="invoice_preview.pdf"'
		return response
	except Exception:
		return HttpResponse(html_string, content_type='text/html')


@login_required
def invoice_create(request):
	# Ensure `businesses` is always defined for rendering the template,
	# even when POST handling returns early due to validation errors.
	businesses = get_businesses_for_user(request.user)
	if request.method == 'POST':
		# If the user typed a new client name instead of selecting an existing client,
		# create that Client first so the InvoiceForm (which requires `client` FK)
		# can validate correctly.
		post_data = request.POST.copy()
		client_field = post_data.get('client') or ''
		# Accept typed client name from the editable `client_name` field when the
		# client select isn't used. This allows saving without choosing an existing
		# Client from the dropdown.
		new_client_name = post_data.get('id_client_create') or post_data.get('client_name') or ''
		if (not client_field) and new_client_name:
			# create lightweight client record
			client = Client.objects.create(
				user=request.user,
				name=new_client_name,
				email=post_data.get('client_email') or post_data.get('id_client_email') or '',
				phone=post_data.get('client_phone') or post_data.get('id_client_phone') or '',
				address=post_data.get('client_address') or post_data.get('id_client_address') or ''
			)
			post_data['client'] = str(client.pk)

		# include uploaded files so file inputs (business photo etc.) are processed
		form = InvoiceForm(post_data, request.FILES, user=request.user)
		# create a bound formset (include files) so uploaded file fields in formset are handled
		formset = InvoiceItemFormSet(request.POST, request.FILES)

		if form.is_valid():
			invoice = form.save(commit=False)
			invoice.user = request.user

			# Read any business fields submitted so we can populate the invoice snapshot
			biz_id = post_data.get('business_id') or post_data.get('business') or ''
			biz_name = post_data.get('business_name') or post_data.get('id_business_name_text') or ''
			biz_email = post_data.get('business_email') or post_data.get('id_business_email_text') or ''
			biz_phone = post_data.get('business_phone') or post_data.get('id_business_phone_text') or ''
			biz_addr = post_data.get('business_address') or post_data.get('id_business_address_text') or ''

			# populate business snapshot fields on the invoice so the PDF/preview
			# remains the same even if the user's BusinessProfile changes later
			if biz_name:
				invoice.business_name = biz_name
			if biz_email:
				invoice.business_email = biz_email
			if biz_phone:
				invoice.business_phone = biz_phone
			if biz_addr:
				invoice.business_address = biz_addr
			# Business photo upload removed from invoice flow; users should edit
			# their BusinessProfile to update the canonical logo instead.
			# Handle client creation when a new client name was typed instead of selecting existing client
			try:
				client_field = request.POST.get('client') or ''
				new_client_name = request.POST.get('id_client_create') or request.POST.get('client_name') or ''
				if (not client_field) and new_client_name:
					# create lightweight client record and attach
					client = Client.objects.create(
						user=request.user,
						name=new_client_name,
						email=request.POST.get('client_email') or request.POST.get('id_client_email') or '',
						phone=request.POST.get('client_phone') or request.POST.get('id_client_phone') or '',
						address=request.POST.get('client_address') or request.POST.get('id_client_address') or ''
					)
					# attach to invoice if model has a client relation
					try: setattr(invoice, 'client', client)
					except Exception: pass
				elif client_field:
					try:
						cobj = Client.objects.filter(pk=int(client_field), user=request.user).first()
						if cobj:
							try: setattr(invoice, 'client', cobj)
							except Exception: pass
					except Exception:
						pass
			except Exception:
				pass
			
			# Persist or update a BusinessProfile snapshot if provided (and attach to invoice if possible)
			biz_id = request.POST.get('business_id') or request.POST.get('business') or ''
			biz_name = request.POST.get('business_name') or request.POST.get('id_business_name_text') or ''
			biz_email = request.POST.get('business_email') or request.POST.get('id_business_email_text') or ''
			biz_phone = request.POST.get('business_phone') or request.POST.get('id_business_phone_text') or ''
			biz_addr = request.POST.get('business_address') or request.POST.get('id_business_address_text') or ''
			bp_obj = None
			try:
				# Try to resolve an existing business by id first (respect visibility rules)
				if biz_id:
					try:
						bp_obj = get_business_or_404_for_user(int(biz_id), request.user)
					except Exception:
						bp_obj = None
				# If no matching id, but a name was provided, get or create by name for this user
				if not bp_obj and biz_name:
					bp_obj, created = BusinessProfile.objects.get_or_create(
						user=request.user,
						business_name=biz_name,
						defaults={'email': biz_email or None, 'phone': biz_phone or None, 'address': biz_addr or None}
					)
				# If we have a BusinessProfile instance, update any provided fields and save
				if bp_obj:
					updated = False
					if biz_name and bp_obj.business_name != biz_name:
						bp_obj.business_name = biz_name; updated = True
					if biz_email and bp_obj.email != biz_email:
						bp_obj.email = biz_email; updated = True
					if biz_phone and bp_obj.phone != biz_phone:
						bp_obj.phone = biz_phone; updated = True
					if biz_addr and bp_obj.address != biz_addr:
						bp_obj.address = biz_addr; updated = True
					# Do NOT copy invoice-uploaded business photo into the canonical BusinessProfile here.
					# Invoice-level photo should be invoice-specific only and saved to Invoice.business_logo.
					# Always save if we created the object or if any provided fields changed
					if updated or (bp_obj.pk and not bp_obj.created_at):
						bp_obj.save()

				# Ensure invoice snapshot fields reflect the selected BusinessProfile when a profile was chosen
				if bp_obj:
					if not invoice.business_name:
						invoice.business_name = bp_obj.business_name or invoice.business_name
					if not invoice.business_email:
						invoice.business_email = bp_obj.email or invoice.business_email
					if not invoice.business_phone:
						invoice.business_phone = bp_obj.phone or invoice.business_phone
					if not invoice.business_address:
						invoice.business_address = bp_obj.address or invoice.business_address
					# If the BusinessProfile has a logo and the invoice doesn't, reference it on the invoice
					try:
						if getattr(bp_obj, 'logo', None) and not getattr(invoice, 'business_logo', None):
							# Assign the underlying storage name so the file is referenced for the invoice
							try:
								invoice.business_logo.name = bp_obj.logo.name
							except Exception:
								invoice.business_logo = bp_obj.logo
					except Exception:
						pass
			except Exception:
				# don't let business profile failures block invoice saving
				bp_obj = None

			try:
				invoice.save()
			except IntegrityError as e:
				# Handle duplicate invoice_number (unique constraint) gracefully
				msg = str(e)
				if 'invoice_number' in msg or 'duplicate key' in msg.lower() or 'unique' in msg.lower():
					# Attach form error so template shows inline validation
					form.add_error('invoice_number', 'Invoice number already exists. Please choose a different invoice number.')
				else:
					form.add_error(None, 'Failed to save invoice: ' + msg)
				# If this was an AJAX save request, return a JSON error so frontend can handle it
				if request.headers.get('x-requested-with') == 'XMLHttpRequest':
					return JsonResponse({'ok': False, 'error': 'save_failed', 'message': str(msg)}, status=400)
				# Fall through to re-render form with errors
			# bind formset to the saved invoice instance and validate/save
			formset = InvoiceItemFormSet(request.POST, request.FILES, instance=invoice)
			if formset.is_valid():
				formset.save()
				invoice.recalc_totals()
				# If an AJAX download-after-save was requested, return JSON with the new PK
				download_after = (request.POST.get('download_after_save') == '1' or request.POST.get('download_after_save') == 'true')
				if download_after and request.headers.get('x-requested-with') == 'XMLHttpRequest':
					return JsonResponse({'ok': True, 'pk': invoice.pk})
				messages.success(request, 'Invoice created.')
				return redirect('invoice_list')
			else:
				# surface formset errors to help debug client-side issues
				msgs = []
				for fs_err in formset.errors:
					if fs_err:
						msgs.append(str(fs_err))
				if msgs:
					messages.error(request, 'Invoice items errors: ' + '; '.join(msgs))
				else:
					messages.error(request, 'Please correct the invoice items.')
		else:
			# show form errors for easier debugging
			# If the invoice_number uniqueness error occurred, present a friendly warning
			# and avoid repeating the raw validation message.
			handled_duplicate_invoice = False
			inv_errs = form.errors.get('invoice_number') or []
			for m in inv_errs:
				if 'already exists' in str(m).lower():
					messages.warning(request, 'Invoice number already exists. Please choose a different invoice number or use the auto-generated value.')
					handled_duplicate_invoice = True
					break
			err_msgs = []
			for f, errs in form.errors.items():
				# skip the raw invoice_number message if we've shown a friendly warning
				if handled_duplicate_invoice and f == 'invoice_number':
					continue
				err_msgs.append(f + ': ' + '; '.join(errs))
			if err_msgs:
				messages.error(request, 'Form errors: ' + ' | '.join(err_msgs))
			else:
				messages.error(request, 'Please correct the errors below.')
	else:
		# prefill invoice number
		last = Invoice.objects.filter(user=request.user).order_by('-id').first()
		if last:
			try:
				next_num = f"INV-{last.id + 1:05d}"
			except Exception:
				next_num = 'INV-00001'
		else:
			next_num = 'INV-00001'
		# default invoice_date and currency to avoid required-field validation errors when user omits them
		form = InvoiceForm(initial={'invoice_number': next_num, 'invoice_date': date.today(), 'currency': 'USD'}, user=request.user)
		formset = InvoiceItemFormSet()

		businesses = get_businesses_for_user(request.user)
	# Provide empty invoice and business_initial to keep template lookups safe
	empty_invoice = Invoice()
	business_initial = {'id': '', 'name': '', 'email': '', 'phone': '', 'address': '', 'logo_url': ''}
	return render(request, 'invoices/invoice_form.html', {'form': form, 'formset': formset, 'action': 'Create', 'businesses': businesses, 'business_initial': business_initial, 'invoice': empty_invoice})


@login_required
def invoice_detail(request, pk):
	invoice = get_invoice_or_404_for_user(pk, request.user)
	# Prefer invoice-level snapshot/logo when present so the view matches PDF output.
	from types import SimpleNamespace
	business = None
	try:
		if getattr(invoice, 'business_name', None) or getattr(invoice, 'business_logo', None):
			biz_logo = None
			try:
				if invoice.business_logo:
					u = invoice.business_logo.url
					if u and not u.startswith('http') and not u.startswith('data:'):
						u = request.build_absolute_uri(u)
					biz_logo = SimpleNamespace(url=u)
			except Exception:
				biz_logo = None
			business = SimpleNamespace(
				business_name=getattr(invoice, 'business_name', '') or '',
				email=getattr(invoice, 'business_email', '') or '',
				phone=getattr(invoice, 'business_phone', '') or '',
				address=getattr(invoice, 'business_address', '') or '',
				logo=biz_logo,
			)
		else:
			bp = get_businesses_for_user(request.user).first()
			if bp:
				try:
					u = bp.logo.url if getattr(bp, 'logo', None) else None
					if u and not u.startswith('http') and not u.startswith('data:'):
						u = request.build_absolute_uri(u)
					biz_logo = SimpleNamespace(url=u) if u else None
				except Exception:
					biz_logo = None
				business = SimpleNamespace(
					business_name=getattr(bp, 'business_name', '') or '',
					email=getattr(bp, 'email', '') or '',
					phone=getattr(bp, 'phone', '') or '',
					address=getattr(bp, 'address', '') or '',
					logo=biz_logo,
				)
			else:
				business = None
	except Exception:
		business = get_businesses_for_user(request.user).first()

	return render(request, 'invoices/invoice_detail.html', {'invoice': invoice, 'business': business})


@login_required
def superadmin_dashboard(request):
	# Only superusers may access
	if not getattr(request.user, 'is_superuser', False):
		return HttpResponseForbidden('Forbidden')

	User = get_user_model()
	q = request.GET.get('q', '').strip()
	page = int(request.GET.get('page', 1) or 1)

	users_qs = User.objects.all().order_by('-date_joined')
	if q:
		users_qs = users_qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))

	paginator = Paginator(users_qs, 25)
	users_page = paginator.get_page(page)

	# Analytics
	total_users = User.objects.count()
	active_users = User.objects.filter(is_active=True).count()
	staff_users = User.objects.filter(is_staff=True).count()
	superusers = User.objects.filter(is_superuser=True).count()
	thirty_days_ago = timezone.now() - timedelta(days=30)
	active_last_30 = User.objects.filter(last_login__gte=thirty_days_ago).count()

	# Activity logs (may be absent on some deployments; handle gracefully)
	log_q = request.GET.get('log_q', '').strip()
	log_user = request.GET.get('log_user', '').strip()
	logs_page = None
	logs_missing = False
	try:
		logs_qs = UsersActivityLog.objects.all().order_by('-timestamp')
		if log_user:
			try:
				logs_qs = logs_qs.filter(user_id=int(log_user))
			except Exception:
				pass
		if log_q:
			logs_qs = logs_qs.filter(Q(activity_type__icontains=log_q) | Q(related_invoice__icontains=log_q))
		log_page_num = int(request.GET.get('log_page', 1) or 1)
		log_paginator = Paginator(logs_qs, 50)
		logs_page = log_paginator.get_page(log_page_num)
	except (DatabaseError, ProgrammingError) as e:
		# Table may not exist; show empty page and flag missing state for template
		logs_missing = True
		logs_page = Paginator([], 50).get_page(1)

	context = {
		'users_page': users_page,
		'q': q,
		'total_users': total_users,
		'active_users': active_users,
		'staff_users': staff_users,
		'superusers': superusers,
		'active_last_30': active_last_30,
		'logs_page': logs_page,
		'log_q': log_q,
		'log_user': log_user,
		'logs_missing': logs_missing,
	}
	return render(request, 'superadmin/dashboard.html', context)


@login_required
def superadmin_log_detail(request, activity_id):
	if not getattr(request.user, 'is_superuser', False):
		return HttpResponseForbidden('Forbidden')
	try:
		log = UsersActivityLog.objects.get(activity_id=activity_id)
	except UsersActivityLog.DoesNotExist:
		from django.http import Http404
		raise Http404('Activity log not found')
	return render(request, 'superadmin/log_detail.html', {'log': log})


@login_required
def superadmin_activity(request):
	if not getattr(request.user, 'is_superuser', False):
		return HttpResponseForbidden('Forbidden')
	q = request.GET.get('q', '').strip()
	user_filter = request.GET.get('user', '').strip()
	page = int(request.GET.get('page', 1) or 1)

	logs_missing = False
	logs_page = None
	try:
		logs_qs = UsersActivityLog.objects.all().order_by('-timestamp')
		if user_filter:
			try:
				logs_qs = logs_qs.filter(user_id=int(user_filter))
			except Exception:
				pass
		if q:
			logs_qs = logs_qs.filter(Q(activity_type__icontains=q) | Q(related_invoice__icontains=q))
		paginator = Paginator(logs_qs, 50)
		logs_page = paginator.get_page(page)
	except (DatabaseError, ProgrammingError):
		logs_missing = True
		logs_page = Paginator([], 50).get_page(1)

	return render(request, 'superadmin/activity_recent.html', {'logs_page': logs_page, 'q': q, 'user_filter': user_filter, 'logs_missing': logs_missing})


@login_required
@require_POST
def toggle_user_active(request, pk):
	if not getattr(request.user, 'is_superuser', False):
		return HttpResponseForbidden('Forbidden')
	User = get_user_model()
	try:
		u = User.objects.get(pk=pk)
		u.is_active = not u.is_active
		u.save(update_fields=['is_active'])
		return redirect(request.META.get('HTTP_REFERER') or reverse('superadmin_dashboard'))
	except User.DoesNotExist:
		messages.error(request, 'User not found.')
		return redirect(request.META.get('HTTP_REFERER') or reverse('superadmin_dashboard'))


@login_required
def superadmin_user_invoices(request, user_id):
	if not getattr(request.user, 'is_superuser', False):
		return HttpResponseForbidden('Forbidden')
	User = get_user_model()
	target_user = get_object_or_404(User, pk=user_id)

	q = request.GET.get('q', '').strip()
	status = request.GET.get('status', '').strip()
	page = int(request.GET.get('page', 1) or 1)

	invoices_qs = Invoice.objects.filter(user=target_user, is_deleted=False)
	if q:
		invoices_qs = invoices_qs.filter(Q(invoice_number__icontains=q) | Q(client__name__icontains=q))
	if status:
		invoices_qs = invoices_qs.filter(status=status)

	paginator = Paginator(invoices_qs.order_by('-created_at'), 25)
	invoices_page = paginator.get_page(page)

	context = {
		'invoices_page': invoices_page,
		'q': q,
		'status': status,
		'target_user': target_user,
	}
	return render(request, 'superadmin/user_invoices.html', context)


@login_required
def superadmin_all_invoices(request):
	if not getattr(request.user, 'is_superuser', False):
		return HttpResponseForbidden('Forbidden')

	q = request.GET.get('q', '').strip()
	status = request.GET.get('status', '').strip()
	user_filter = request.GET.get('user', '').strip()
	page = int(request.GET.get('page', 1) or 1)

	invoices_qs = Invoice.objects.filter(is_deleted=False)
	if user_filter:
		try:
			invoices_qs = invoices_qs.filter(user_id=int(user_filter))
		except Exception:
			pass
	if q:
		invoices_qs = invoices_qs.filter(Q(invoice_number__icontains=q) | Q(client__name__icontains=q))
	if status:
		invoices_qs = invoices_qs.filter(status=status)

	paginator = Paginator(invoices_qs.order_by('-created_at'), 25)
	invoices_page = paginator.get_page(page)

	context = {
		'invoices_page': invoices_page,
		'q': q,
		'status': status,
		'user_filter': user_filter,
	}
	return render(request, 'superadmin/all_invoices.html', context)


@login_required
def superadmin_businesses(request):
	if not getattr(request.user, 'is_superuser', False):
		return HttpResponseForbidden('Forbidden')
	q = request.GET.get('q', '').strip()
	user_filter = request.GET.get('user', '').strip()
	page = int(request.GET.get('page', 1) or 1)

	qs = BusinessProfile.objects.filter(is_deleted=False)
	if user_filter:
		try:
			qs = qs.filter(user_id=int(user_filter))
		except Exception:
			pass
	if q:
		qs = qs.filter(Q(business_name__icontains=q) | Q(email__icontains=q))

	paginator = Paginator(qs.order_by('-created_at'), 25)
	page_obj = paginator.get_page(page)
	return render(request, 'superadmin/businesses.html', {'page_obj': page_obj, 'q': q, 'user_filter': user_filter})


@login_required
def superadmin_clients(request):
	if not getattr(request.user, 'is_superuser', False):
		return HttpResponseForbidden('Forbidden')
	q = request.GET.get('q', '').strip()
	user_filter = request.GET.get('user', '').strip()
	page = int(request.GET.get('page', 1) or 1)

	qs = Client.objects.filter(is_deleted=False)
	if user_filter:
		try:
			qs = qs.filter(user_id=int(user_filter))
		except Exception:
			pass
	if q:
		qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q))

	paginator = Paginator(qs.order_by('-created_at'), 25)
	page_obj = paginator.get_page(page)
	return render(request, 'superadmin/clients.html', {'page_obj': page_obj, 'q': q, 'user_filter': user_filter})


@login_required
def superadmin_manage_superadmins(request):
	if not getattr(request.user, 'is_superuser', False):
		return HttpResponseForbidden('Forbidden')
	User = get_user_model()
	q = request.GET.get('q', '').strip()
	page = int(request.GET.get('page', 1) or 1)

	qs = User.objects.filter(is_superuser=True).order_by('-date_joined')
	if q:
		qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))

	paginator = Paginator(qs, 25)
	page_obj = paginator.get_page(page)

	return render(request, 'superadmin/manage_superadmins.html', {'page_obj': page_obj, 'q': q})


@login_required
def superadmin_edit_superadmin(request, user_id):
	if not getattr(request.user, 'is_superuser', False):
		return HttpResponseForbidden('Forbidden')
	User = get_user_model()
	target = get_object_or_404(User, pk=user_id, is_superuser=True)

	if request.method == 'POST':
		new_password = request.POST.get('new_password', '').strip()
		confirm = request.POST.get('confirm_password', '').strip()
		if not new_password:
			messages.error(request, 'Password cannot be empty.')
		elif new_password != confirm:
			messages.error(request, 'Passwords do not match.')
		else:
			target.set_password(new_password)
			target.save(update_fields=['password'])
			messages.success(request, 'Password updated.')
			return redirect(request.META.get('HTTP_REFERER') or reverse('superadmin_manage_superadmins'))

	return render(request, 'superadmin/edit_superadmin.html', {'target': target})


@login_required
@require_POST
def superadmin_toggle_active_superadmin(request, user_id):
	if not getattr(request.user, 'is_superuser', False):
		return HttpResponseForbidden('Forbidden')
	User = get_user_model()
	try:
		target = User.objects.get(pk=user_id, is_superuser=True)
	except User.DoesNotExist:
		messages.error(request, 'Superadmin not found.')
		return redirect(request.META.get('HTTP_REFERER') or reverse('superadmin_manage_superadmins'))

	# Prevent deactivating self to avoid lockout
	if target.pk == request.user.pk:
		messages.error(request, 'You cannot deactivate your own account.')
		return redirect(request.META.get('HTTP_REFERER') or reverse('superadmin_manage_superadmins'))

	# Ensure at least one active superuser remains
	active_supers = User.objects.filter(is_superuser=True, is_active=True).count()
	if target.is_active and active_supers <= 1:
		messages.error(request, 'Cannot deactivate the last active superadmin.')
		return redirect(request.META.get('HTTP_REFERER') or reverse('superadmin_manage_superadmins'))

	target.is_active = not target.is_active
	target.save(update_fields=['is_active'])
	return redirect(request.META.get('HTTP_REFERER') or reverse('superadmin_manage_superadmins'))


@login_required
def invoice_edit(request, pk):
	invoice = get_invoice_or_404_for_user(pk, request.user)

	# capture original business snapshot so form binding doesn't clobber missing fields
	orig_business_name = invoice.business_name
	orig_business_email = invoice.business_email
	orig_business_phone = invoice.business_phone
	orig_business_address = invoice.business_address
	orig_business_logo = getattr(invoice, 'business_logo', None)
	# formset class for editing: no extra blank forms
	InvoiceItemFormSetEdit = inlineformset_factory(Invoice, InvoiceItem, form=InvoiceItemForm, extra=0, can_delete=True)
	if request.method == 'POST':
		# allow creating a new client by text input (same behavior as invoice_create)
		post_data = request.POST.copy()
		client_field = post_data.get('client') or ''
		# Allow the edit view to accept a manually-typed client name as well
		new_client_name = post_data.get('id_client_create') or post_data.get('client_name') or ''
		if (not client_field) and new_client_name:
			client = Client.objects.create(
				user=request.user,
				name=new_client_name,
				email=post_data.get('client_email') or post_data.get('id_client_email') or '',
				phone=post_data.get('client_phone') or post_data.get('id_client_phone') or '',
				address=post_data.get('client_address') or post_data.get('id_client_address') or ''
			)
			post_data['client'] = str(client.pk)

		# bind forms to the (possibly modified) POST so client selection validates
		form = InvoiceForm(post_data, request.FILES, instance=invoice)
		formset = InvoiceItemFormSetEdit(post_data, request.FILES, instance=invoice)

		if form.is_valid() and formset.is_valid():
			invoice = form.save(commit=False)
			invoice.user = request.user

			# update/create BusinessProfile (do not attach to invoice model)
			biz_id = post_data.get('business_id') or post_data.get('business') or ''
			biz_name = post_data.get('business_name') or post_data.get('id_business_name_text') or ''
			biz_email = post_data.get('business_email') or post_data.get('id_business_email_text') or ''
			biz_phone = post_data.get('business_phone') or post_data.get('id_business_phone_text') or ''
			biz_addr = post_data.get('business_address') or post_data.get('id_business_address_text') or ''
			try:
				if biz_id:
					try:
						bp = get_business_or_404_for_user(int(biz_id), request.user)
					except Exception:
						bp = None
					if bp:
						if biz_name: bp.business_name = biz_name
						if biz_email: bp.email = biz_email
						if biz_phone: bp.phone = biz_phone
						if biz_addr: bp.address = biz_addr
						# Do NOT update BusinessProfile.logo from invoice edit uploads.
						bp.save()
				else:
					if biz_name:
						bp, created = BusinessProfile.objects.get_or_create(user=request.user, business_name=biz_name, defaults={'email': biz_email or None, 'phone': biz_phone or None, 'address': biz_addr or None})
						if not created:
							updated = False
							if biz_email and bp.email != biz_email:
								bp.email = biz_email; updated = True
							if biz_phone and bp.phone != biz_phone:
								bp.phone = biz_phone; updated = True
							if biz_addr and bp.address != biz_addr:
								bp.address = biz_addr; updated = True
							# Do NOT update BusinessProfile.logo from invoice edit uploads.
							if updated:
								bp.save()
			except Exception:
				# don't block invoice save on business profile errors
				pass

			# populate business snapshot for edited invoice as well
			if biz_name:
				invoice.business_name = biz_name
			if biz_email:
				invoice.business_email = biz_email
			if biz_phone:
				invoice.business_phone = biz_phone
			if biz_addr:
				invoice.business_address = biz_addr
			# If no editable snapshot was provided, preserve original values (don't clear them)
			if not biz_name and orig_business_name:
				invoice.business_name = orig_business_name
			if not biz_email and orig_business_email:
				invoice.business_email = orig_business_email
			if not biz_phone and orig_business_phone:
				invoice.business_phone = orig_business_phone
			if not biz_addr and orig_business_address:
				invoice.business_address = orig_business_address
			# If a BusinessProfile was selected and invoice lacks a logo, copy it
			try:
				try:
					if 'bp' in locals() and bp and getattr(bp, 'logo', None) and not getattr(invoice, 'business_logo', None):
						try:
							invoice.business_logo.name = bp.logo.name
						except Exception:
							invoice.business_logo = bp.logo
				except Exception:
					pass
			except Exception:
				pass
			# Business photo upload removed from invoice flow; users should edit
			# their BusinessProfile to update the canonical logo instead.

			invoice.save()
			formset.save()
			invoice.recalc_totals()
			messages.success(request, 'Invoice updated.')
			return redirect('invoice_detail', pk=invoice.pk)
		else:
			# surface errors to help debugging
			if not form.is_valid():
				errs = []
				for f, e in form.errors.items():
					errs.append(f + ': ' + '; '.join(e))
				messages.error(request, 'Form errors: ' + ' | '.join(errs))
			if not formset.is_valid():
				msgs = []
				for fe in formset.errors:
					if fe:
						msgs.append(str(fe))
				if msgs:
					messages.error(request, 'Formset errors: ' + '; '.join(msgs))
	else:
		form = InvoiceForm(instance=invoice)
		# For edit view, avoid showing an extra blank invoice item
		formset = InvoiceItemFormSetEdit(instance=invoice)
	businesses = get_businesses_for_user(request.user)

	# Prepare initial values for the business fields so editing an invoice preserves values
	business_initial = {'id': '', 'name': '', 'email': '', 'phone': '', 'address': '', 'logo_url': ''}
	if 'post_data' in locals():
		# POST (possibly invalid) - prefer posted values so the user doesn't lose edits
		business_initial['id'] = post_data.get('business_id') or post_data.get('business') or ''
		business_initial['name'] = post_data.get('business_name') or post_data.get('id_business_name_text') or ''
		business_initial['email'] = post_data.get('business_email') or post_data.get('id_business_email_text') or ''
		business_initial['phone'] = post_data.get('business_phone') or post_data.get('id_business_phone_text') or ''
		business_initial['address'] = post_data.get('business_address') or post_data.get('id_business_address_text') or ''
	else:
		# GET - populate from saved invoice snapshot or match an existing BusinessProfile by name
		business_initial['name'] = invoice.business_name or ''
		business_initial['email'] = invoice.business_email or ''
		business_initial['phone'] = invoice.business_phone or ''
		business_initial['address'] = invoice.business_address or ''
		if invoice.business_logo:
			try:
				u = invoice.business_logo.url
				if u and not u.startswith('http') and not u.startswith('data:'):
					u = request.build_absolute_uri(u)
				business_initial['logo_url'] = u
			except Exception:
				business_initial['logo_url'] = ''
			# try to resolve a matching BusinessProfile so the select can default to it
			if business_initial['name']:
				bp = get_businesses_for_user(request.user).filter(business_name=business_initial['name']).first()
			if bp:
				business_initial['id'] = bp.pk
				if bp.logo:
					try:
						u = bp.logo.url
						if u and not u.startswith('http') and not u.startswith('data:'):
							u = request.build_absolute_uri(u)
						business_initial['logo_url'] = u
					except Exception:
						pass

	return render(request, 'invoices/invoice_form.html', {'form': form, 'formset': formset, 'action': 'Edit', 'businesses': businesses, 'business_initial': business_initial, 'invoice': invoice})


@login_required
def invoice_delete(request, pk):
	invoice = get_invoice_or_404_for_user(pk, request.user)
	if request.method == 'POST':
		moved = _move_invoice_to_trash(pk, user=request.user)
		if moved:
			messages.success(request, 'Invoice moved to trash.')
		else:
			messages.error(request, 'Failed to move invoice to trash.')
		return redirect('invoice_list')
	return render(request, 'invoices/invoice_confirm_delete.html', {'invoice': invoice})


@login_required
def invoice_confirmation(request, pk):
	invoice = get_invoice_or_404_for_user(pk, request.user)
	return render(request, 'invoices/invoice_confirmation.html', {'invoice': invoice})


@login_required
def generate_pdf(request, pk):
	invoice = get_invoice_or_404_for_user(pk, request.user)
	# Prefer invoice-level snapshot/logo when present so each invoice's PDF reflects
	# the selected/uploaded image. Fall back to the user's BusinessProfile otherwise.
	from types import SimpleNamespace
	business = None
	try:
		if getattr(invoice, 'business_name', None) or getattr(invoice, 'business_logo', None):
			biz_logo = None
			try:
				if invoice.business_logo:
					u = invoice.business_logo.url
					if u and not u.startswith('http') and not u.startswith('data:'):
						u = request.build_absolute_uri(u)
					biz_logo = SimpleNamespace(url=u)
			except Exception:
				biz_logo = None
			business = SimpleNamespace(
				business_name=getattr(invoice, 'business_name', '') or '',
				email=getattr(invoice, 'business_email', '') or '',
				phone=getattr(invoice, 'business_phone', '') or '',
				address=getattr(invoice, 'business_address', '') or '',
				logo=biz_logo,
			)
		else:
			bp = get_businesses_for_user(request.user).first()
			if bp:
				try:
					u = bp.logo.url if getattr(bp, 'logo', None) else None
					if u and not u.startswith('http') and not u.startswith('data:'):
						u = request.build_absolute_uri(u)
					biz_logo = SimpleNamespace(url=u) if u else None
				except Exception:
					biz_logo = None
				business = SimpleNamespace(
					business_name=getattr(bp, 'business_name', '') or '',
					email=getattr(bp, 'email', '') or '',
					phone=getattr(bp, 'phone', '') or '',
					address=getattr(bp, 'address', '') or '',
					logo=biz_logo,
				)
			else:
				business = None

	except Exception:
		business = get_businesses_for_user(request.user).first()

	# render with request so template tags that rely on request (static, media) resolve correctly
	html_string = render_to_string('invoices/invoice_pdf.html', {'invoice': invoice, 'business': business}, request=request)

	# Allow forcing a specific backend via ?backend=wkhtmltopdf
	backend = (request.GET.get('backend') or '').lower()
	prefer_wk = backend == 'wkhtmltopdf'

	# Try to import WeasyPrint unless the caller specifically requested wkhtmltopdf
	weasy_error = None
	HTML = None
	if not prefer_wk:
		try:
			from weasyprint import HTML
		except Exception as e:
			HTML = None
			weasy_error = str(e)

	# If WeasyPrint is available and not overridden, use it.
	if HTML:
		try:
			html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
			pdf = html.write_pdf()
			response = HttpResponse(pdf, content_type='application/pdf')
			if request.GET.get('format') == 'pdf':
				response['Content-Disposition'] = f'attachment; filename="invoice-{invoice.invoice_number}.pdf"'
			else:
				response['Content-Disposition'] = f'inline; filename="invoice-{invoice.invoice_number}.pdf"'
			return response
		except Exception as e:
			weasy_error = (weasy_error or '') + '\n' + str(e)

	# WeasyPrint not available or failed — attempt wkhtmltopdf fallback.
	wk_cmd_setting = getattr(settings, 'WKHTMLTOPDF_CMD', None)
	candidates = []
	if wk_cmd_setting:
		candidates.append(wk_cmd_setting)
	# prefer PATH lookup
	try:
		found = shutil.which('wkhtmltopdf')
		if found:
			candidates.append(found)
	except Exception:
		pass

	# common locations (Windows / Linux)
	candidates.extend([
		r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
		r'C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe',
		'/usr/local/bin/wkhtmltopdf',
		'/usr/bin/wkhtmltopdf',
	])

	wk_error = None
	used_cmd = None
	for cmd in candidates:
		if not cmd:
			continue
		# If cmd is an explicit path, check file exists; if it's a name, shutil.which will help
		try:
			if os.path.isfile(cmd) or shutil.which(cmd):
				used_cmd = cmd
				break
		except Exception:
			continue

	if used_cmd:
		try:
			# write HTML to temp file and generate PDF using wkhtmltopdf
			# Ensure resource URLs (media/static) are absolute so wkhtmltopdf can fetch them
			base_url = request.build_absolute_uri('/')
			html_for_wk = html_string.replace('src="/', f'src="{base_url}').replace("src='/", f"src='{base_url}")
			html_for_wk = html_for_wk.replace('href="/', f'href="{base_url}').replace("href='/", f"href='{base_url}")
			html_for_wk = html_for_wk.replace("url('/", f"url('{base_url}").replace('url("/', f'url("{base_url}')

			with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as fh:
				fh.write(html_for_wk.encode('utf-8'))
				fh.flush()
				tmp_html = fh.name
			tmp_pdf = tmp_html + '.pdf'
			# Ensure we enable local file access for complex templates
			proc = subprocess.run([used_cmd, '--enable-local-file-access', tmp_html, tmp_pdf], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
			if proc.returncode == 0 and os.path.exists(tmp_pdf):
				with open(tmp_pdf, 'rb') as f:
					pdf = f.read()
				try:
					os.unlink(tmp_html)
				except Exception:
					pass
				try:
					os.unlink(tmp_pdf)
				except Exception:
					pass
				response = HttpResponse(pdf, content_type='application/pdf')
				if request.GET.get('format') == 'pdf':
					response['Content-Disposition'] = f'attachment; filename="invoice-{invoice.invoice_number}.pdf"'
				else:
					response['Content-Disposition'] = f'inline; filename="invoice-{invoice.invoice_number}.pdf"'
				return response
			else:
				wk_error = proc.stderr.decode('utf-8', errors='replace')
		except Exception as e:
			wk_error = str(e)

	# If we reach here, no PDF backend produced a PDF. Provide informative HTML fallback
	messages_html = ['PDF generation is currently unavailable.']
	if weasy_error:
		messages_html.append('<strong>WeasyPrint error:</strong> ' + str(weasy_error))
	if used_cmd:
		messages_html.append('<strong>Attempted wkhtmltopdf:</strong> ' + str(used_cmd))
	if wk_error:
		messages_html.append('<strong>wkhtmltopdf error:</strong> ' + str(wk_error))
	if not used_cmd:
		messages_html.append('wkhtmltopdf not found on system PATH or common locations.')
	messages_html.append('To enable PDF downloads, install WeasyPrint with its native dependencies OR install wkhtmltopdf and add it to PATH or set <code>WKHTMLTOPDF_CMD</code> in settings.')

	diagnostic = '<br/>'.join(messages_html)
	html_with_diag = f'<div class="alert alert-warning" style="margin:12px;">{diagnostic}</div>' + html_string
	return HttpResponse(html_with_diag, content_type='text/html')
	try:
		html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
		pdf = html.write_pdf()
		response = HttpResponse(pdf, content_type='application/pdf')
		response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
		try:
			# mark as generated and persist only the pdf_generated flag
			invoice.pdf_generated = True
			invoice.save(update_fields=['pdf_generated'])
		except Exception:
			# don't let a secondary save error break PDF delivery
			pass
		return response
	except Exception:
		messages.error(request, 'Failed to generate PDF. Showing HTML preview instead.')
		return HttpResponse(html_string, content_type='text/html')


@login_required
def pdf_status(request):
	"""Diagnostic endpoint: reports availability of WeasyPrint and wkhtmltopdf."""
	status = {'weasyprint': {'available': False, 'version': None, 'error': None}, 'wkhtmltopdf': {'found': False, 'path': None, 'version': None, 'error': None}, 'settings_WKHTMLTOPDF_CMD': getattr(settings, 'WKHTMLTOPDF_CMD', None)}
	try:
		import weasyprint
		status['weasyprint']['available'] = True
		try:
			status['weasyprint']['version'] = getattr(weasyprint, '__version__', str(weasyprint))
		except Exception:
			status['weasyprint']['version'] = 'unknown'
	except Exception as e:
		status['weasyprint']['error'] = str(e)

	try:
		wk_cmd = shutil.which('wkhtmltopdf') or getattr(settings, 'WKHTMLTOPDF_CMD', None)
		if wk_cmd:
			status['wkhtmltopdf']['found'] = True
			status['wkhtmltopdf']['path'] = wk_cmd
			try:
				p = subprocess.run([wk_cmd, '--version'], capture_output=True, text=True, timeout=5)
				status['wkhtmltopdf']['version'] = p.stdout.strip() or p.stderr.strip()
			except Exception as e:
				status['wkhtmltopdf']['error'] = str(e)
	except Exception as e:
		status['wkhtmltopdf']['error'] = str(e)

	return JsonResponse(status)


@csrf_exempt
def track_ad_click(request):
	if request.method == 'POST':
		try:
			data = json.loads(request.body)
		except Exception:
			data = {}
		AdClick.objects.create(
			ad_identifier=data.get('ad_id') or data.get('ad_identifier', 'unknown'),
			placement=data.get('placement', ''),
			target_url=data.get('url') or data.get('target_url', ''),
		)
		return JsonResponse({'status': 'ok'})
	return JsonResponse({'status': 'method not allowed'}, status=405)


def exchange_rate(request):
	"""Proxy to exchangerate.host for a simple rate lookup: ?base=USD&target=EUR"""
	base = request.GET.get('base', 'USD').upper()
	target = request.GET.get('target', 'USD').upper()
	if base == target:
		return JsonResponse({'rate': 1.0})
	# Prefer requests if available, otherwise use urllib to avoid adding strict dependency
	try:
		try:
			import requests
			r = requests.get('https://api.exchangerate.host/latest', params={'base': base, 'symbols': target}, timeout=5)
			r.raise_for_status()
			data = r.json()
		except Exception:
			# fallback to urllib
			from urllib.request import urlopen
			from urllib.parse import urlencode
			url = 'https://api.exchangerate.host/latest?' + urlencode({'base': base, 'symbols': target})
			with urlopen(url, timeout=5) as fh:
				import json as _json
				data = _json.load(fh)

		rate = data.get('rates', {}).get(target)
		if rate is None:
			return JsonResponse({'error': 'rate not found'}, status=404)
		return JsonResponse({'rate': rate})
	except Exception as e:
		return JsonResponse({'error': str(e)}, status=500)


@login_required
def email_invoice(request, pk):
	invoice = get_invoice_or_404_for_user(pk, request.user)
	client_email = invoice.client_email or invoice.client.email
	if not client_email:
		messages.error(request, 'Client does not have an email address.')
		return redirect('invoice_detail', pk=pk)

	if request.method == 'POST':
		subject = request.POST.get('subject') or f'Invoice {invoice.invoice_number}'
		message = request.POST.get('message') or 'Please find your invoice attached.'
		from django.core.mail import EmailMessage
		from django.conf import settings

		attachments = []
		# Try to generate PDF; if not possible attach HTML
		html_string = render_to_string('invoices/invoice_pdf.html', {'invoice': invoice, 'business': get_businesses_for_user(request.user).first()})
		try:
			from weasyprint import HTML
			html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
			pdf = html.write_pdf()
			attachments.append((f'invoice_{invoice.invoice_number}.pdf', pdf, 'application/pdf'))
		except Exception:
			# fallback to HTML attachment
			attachments.append((f'invoice_{invoice.invoice_number}.html', html_string.encode('utf-8'), 'text/html'))

		email = EmailMessage(subject=subject, body=message, from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None), to=[client_email])
		for name, content, mimetype in attachments:
			email.attach(name, content, mimetype)

		try:
			email.send()
			messages.success(request, 'Invoice emailed to client.')
		except Exception as e:
			messages.error(request, f'Failed to send email: {e}')

		return redirect('invoice_detail', pk=pk)

	# GET -> show simple send form
	return render(request, 'invoices/email_invoice.html', {'invoice': invoice})

