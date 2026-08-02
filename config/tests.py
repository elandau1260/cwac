"""Project-level tests: URL wiring (health check + root redirect) and the production
SECRET_KEY fail-closed guard.

App-level tests live in each app's tests.py and are filled in across Phases 1-10.
"""
import os
import subprocess
import sys


def test_healthz_returns_ok(client):
    """The Render readiness probe must answer 200 without touching the database."""
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.content == b"ok"


def test_root_redirects_to_admin(client):
    """The bare domain `/` redirects to the admin login (the public form is at /r/<slug>/)."""
    response = client.get("/")
    assert response.status_code == 302
    assert response["Location"] == "/admin/"


def test_prod_settings_reject_insecure_secret_key():
    """Loading prod settings with the dev placeholder SECRET_KEY must fail closed.

    Runs in a subprocess so the already-imported dev settings of this test session are
    not disturbed; a real local .env cannot override an env var set explicitly here.
    """
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "SECRET_KEY": "dev-insecure-change-me",
        "ALLOWED_HOSTS": "example.com",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "prod settings must refuse to load with the placeholder key"
    assert "SECRET_KEY" in result.stderr


def test_prod_settings_reject_missing_secret_key():
    """With no SECRET_KEY at all, prod must also fail closed (not fall back to the placeholder)."""
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "ALLOWED_HOSTS": "example.com",
    }
    env.pop("SECRET_KEY", None)
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr
