"""Production SMS fail-closed check (F7, round-7 audit).

When production sends real SMS (``SMS_BACKEND=twilio``), it must do so through a
Messaging Service (Advanced Opt-Out works only on one) and build edit-links
against the canonical origin. Rather than silently falling back to a bare
from-number or a wrong/stale origin, refuse to boot.

Kept as a pure, side-effect-free function so it can be unit-tested directly
(importing ``config.settings.prod`` itself also runs its SECRET_KEY check).
"""
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured


def validate_twilio_prod_config(
    *, sms_backend, public_base_url, messaging_service_sid
):
    """Raise ``ImproperlyConfigured`` if a twilio prod config is incomplete.

    No-op for any other ``sms_backend`` (dev/test backends don't send real SMS).
    """
    if sms_backend != "twilio":
        return

    base_url = (public_base_url or "").strip()
    sid = (messaging_service_sid or "").strip()
    parsed = urlparse(base_url)

    if not base_url or parsed.scheme != "https" or not parsed.netloc:
        raise ImproperlyConfigured(
            "PUBLIC_BASE_URL must be a valid https:// origin in production when "
            "SMS_BACKEND=twilio (it builds SMS edit-links from the lottery path). "
            "Set the PUBLIC_BASE_URL environment variable."
        )
    if not sid or not sid.startswith("MG"):
        raise ImproperlyConfigured(
            "TWILIO_MESSAGING_SERVICE_SID must be set to an 'MG…' Messaging Service "
            "SID in production when SMS_BACKEND=twilio (production sends go through "
            "it so Advanced Opt-Out works). Set TWILIO_MESSAGING_SERVICE_SID."
        )
