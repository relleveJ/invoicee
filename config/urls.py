from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from invoices import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Authentication
    path('', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    
    # Dashboard
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    # Business Profile
    path('business-profile/', views.business_profile_setup, name='business_profile_setup'),
    path('business-profile/trash/', views.business_trash_list, name='business_trash_list'),
    path('business-profile/trash/restore-edit/<int:trash_pk>/', views.business_restore_and_edit, name='business_restore_and_edit'),
    path('business-profile/trash/restore/<int:trash_pk>/', views.business_restore, name='business_restore'),
    path('business-profile/cancel-restore/<int:business_pk>/', views.business_cancel_restore, name='business_cancel_restore'),
    path('business-profile/bulk-action/', views.business_bulk_action, name='business_bulk_action'),
    
    # Clients
    path('clients/', views.client_list, name='client_list'),
    path('clients/trash/', views.client_trash_list, name='client_trash_list'),
    path('clients/bulk-action/', views.client_bulk_action, name='client_bulk_action'),
    path('clients/add/', views.client_create, name='client_create'),
    path('clients/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('clients/<int:pk>/delete/', views.client_delete, name='client_delete'),
    
    # Invoices
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/trash/', views.invoice_trash_list, name='invoice_trash_list'),
    path('invoices/trash/<int:trash_pk>/', views.invoice_trash_view, name='invoice_trash_view'),
    path('invoices/bulk-action/', views.invoice_bulk_action, name='invoice_bulk_action'),
    path('invoices/create/', views.invoice_create, name='invoice_create'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('invoices/<int:pk>/delete/', views.invoice_delete, name='invoice_delete'),
    path('invoices/<int:pk>/confirmation/', views.invoice_confirmation, name='invoice_confirmation'),
    path('invoices/<int:pk>/pdf/', views.generate_pdf, name='generate_pdf'),
    path('pdf-status/', views.pdf_status, name='pdf_status'),
    path('invoices/<int:pk>/email/', views.email_invoice, name='email_invoice'),
    path('invoices/preview/', views.invoice_live_preview, name='invoice_live_preview'),
    path('clients/<int:pk>/json/', views.client_detail_api, name='client_detail_api'),
    path('businesses/<int:pk>/json/', views.business_detail_api, name='business_detail_api'),
    # Superadmin
    path('superadmin/', views.superadmin_dashboard, name='superadmin_dashboard'),
    path('superadmin/users/<int:pk>/toggle-active/', views.toggle_user_active, name='toggle_user_active'),
    path('superadmin/logs/<int:activity_id>/', views.superadmin_log_detail, name='superadmin_log_detail'),
    path('superadmin/activity/', views.superadmin_activity, name='superadmin_activity'),
    path('superadmin/users/<int:user_id>/invoices/', views.superadmin_user_invoices, name='superadmin_user_invoices'),
    path('superadmin/invoices/', views.superadmin_all_invoices, name='superadmin_all_invoices'),
    path('superadmin/businesses/', views.superadmin_businesses, name='superadmin_businesses'),
    path('superadmin/clients/', views.superadmin_clients, name='superadmin_clients'),
    
    # Ad Tracking
    path('api/track-ad/', views.track_ad_click, name='track_ad_click'),
    path('api/exchange-rate/', views.exchange_rate, name='exchange_rate'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)