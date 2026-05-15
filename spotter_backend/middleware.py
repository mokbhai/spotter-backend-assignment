import time

from routing.services import openpanel


class OpenPanelAPIMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = self.get_response(request)

        if request.path.startswith("/api/") and request.path != "/api/openpanel/config/":
            duration_ms = int((time.perf_counter() - started) * 1000)
            openpanel.track_event(
                "backend_api_call",
                {
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "query_string": request.META.get("QUERY_STRING", ""),
                },
                profile_id=request.headers.get("X-OpenPanel-Profile-Id"),
                client_ip=_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )

        return response


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR")
