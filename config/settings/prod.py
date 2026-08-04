"""Production settings (Render)."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import INSECURE_DEV_SECRET_KEY, SECRET_KEY

DEBUG = False

# Fail closed: production must never run with the dev placeholder SECRET_KEY. Render
# generates SECRET_KEY via render.yaml (generateValue: true); this guard catches a missing
# or misapplied env var so we never sign sessions with a publicly known key.
if not SECRET_KEY or SECRET_KEY == INSECURE_DEV_SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY must be set to a strong, non-default value in production "
        "(config/settings/prod.py). Set the SECRET_KEY environment variable."
    )

# Render terminates TLS at the proxy; trust the forwarded header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# ALLOWED_HOSTS comes from the environment in prod (render.yaml sets it).

# Fail closed on SMS: production must send through a Messaging Service (Advanced
# Opt-Out works only on one) and know its canonical origin. Refuse to boot if
# either is missing/malformed when SMS_BACKEND=twilio, rather than silently
# sending via a bare from-number or building edit-links against the wrong origin.
from ._sms_guard import validate_twilio_prod_config

validate_twilio_prod_config(
    sms_backend=SMS_BACKEND,
    public_base_url=PUBLIC_BASE_URL,
    messaging_service_sid=TWILIO_MESSAGING_SERVICE_SID,
)
