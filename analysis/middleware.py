import time
from django.db import transaction
from .models import RequestLog

EXCLUDED_PATHS = (
    "/static/",
    "/media/",
    "/favicon.ico",
    "/admin/js/",
    "/admin/css/",
)

class RequestLoggingMiddleware:
    """
    Logs request path, user, status, and duration.
    Skips static/admin requests. Async-safe and writes after commit.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(EXCLUDED_PATHS):
            return self.get_response(request)

        start_time = time.time()
        response = self.get_response(request)
        duration_ms = (time.time() - start_time) * 1000

        # defer DB write until after successful transaction
        def log_request():
            RequestLog.objects.create(
                path=request.path,
                method=request.method,
                user=request.user if request.user.is_authenticated else None,
                status_code=response.status_code,
                response_time_ms=duration_ms,
            )

        transaction.on_commit(log_request)
        return response