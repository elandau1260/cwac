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
