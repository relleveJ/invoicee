from django.utils import timezone
from django.db import DatabaseError, ProgrammingError, connection
from .models import UsersActivityLog

class ActivityLogMiddleware:
    """Simple middleware to record user activity into `users_activity_logs`.
    Writes a row for authenticated users on each response. Intentionally
    lightweight and defensive: failures to write the log are swallowed so the
    app continues to function even if the table is missing.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        try:
            user = getattr(request, 'user', None)
            if user and user.is_authenticated:
                # Determine a lightweight activity_type and optional related invoice id
                activity_type = f"{request.method} {request.path}"
                related_invoice = None
                # Try common locations for an invoice id
                try:
                    if 'pk' in request.resolver_match.kwargs:
                        related_invoice = str(request.resolver_match.kwargs.get('pk'))
                except Exception:
                    pass
                if not related_invoice:
                    related_invoice = request.POST.get('invoice_pk') or request.POST.get('id') or request.GET.get('invoice_pk') or request.GET.get('id')

                try:
                    # Insert via raw SQL so DB can assign primary key/autoincrement
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO users_activity_logs (user_id, activity_type, timestamp, related_invoice) VALUES (%s, %s, %s, %s)",
                            [getattr(user, 'id', None) or 0, activity_type, timezone.now(), (related_invoice or None)]
                        )
                except (DatabaseError, ProgrammingError, Exception):
                    # Don't crash if the table doesn't exist or insertion fails
                    pass
        except Exception:
            # Be defensive; never let logging break a request
            pass

        return response
