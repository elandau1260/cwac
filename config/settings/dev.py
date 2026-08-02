"""Development settings — local dev only."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# SMS prints to stdout during local dev.
SMS_BACKEND = "console"
