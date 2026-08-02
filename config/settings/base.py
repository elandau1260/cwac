"""
Base settings shared by dev and prod (Phase 0 scaffolding).

All secrets come from the environment (django-environ). The database is env-driven
via DATABASE_URL (dj-database-url), defaulting to local SQLite for dev convenience.
"""
from pathlib import Path

import dj_database_url
import environ

# cwac/config/settings/base.py -> repo root is three parents up.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)

# Read a local .env file if present (dev convenience). No-op in prod where it's absent.
environ.Env.read_env(str(BASE_DIR / ".env"))

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps (built out across Phases 1-10)
    "accounts",
    "events",
    "register",
    "lottery",
    "sms",
    "clinic",
    "printing",
    "export",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Custom user model. MUST be set before the first migration (Phase 0 -> accounts.User).
AUTH_USER_MODEL = "accounts.User"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"

# Database: env-driven via DATABASE_URL; SQLite fallback so dev runs out of the box.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    ),
}

# Internationalization: public form + SMS are EN/ES; admin/clinic UI is English-only.
LANGUAGE_CODE = "en-us"
LANGUAGE_COOKIE_NAME = "django_language"
LANGUAGES = [
    ("en", "English"),
    ("es", "Spanish"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# SMS backend selector (see sms/ in Phase 3): console | locmem | twilio
SMS_BACKEND = env("SMS_BACKEND", default="console")

# Twilio credentials — env only, used only when SMS_BACKEND == "twilio".
TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID", default="")
TWILIO_AUTH_TOKEN = env("TWILIO_AUTH_TOKEN", default="")
TWILIO_FROM_NUMBER = env("TWILIO_FROM_NUMBER", default="")

# Light observability (Architecture §12): lottery runs, SMS send attempts, print.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
    },
}
