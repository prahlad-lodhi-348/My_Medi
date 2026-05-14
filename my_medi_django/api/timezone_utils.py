from zoneinfo import ZoneInfo
from django.utils import timezone

# timezone function 
def get_request_tz(request):
    tzname = request.headers.get("X-Timezone") or request.GET.get("tz")
    try:
        return ZoneInfo(tzname) if tzname else timezone.get_current_timezone()
    except Exception:
        return timezone.get_current_timezone()