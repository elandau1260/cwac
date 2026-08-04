"""Tests for the production SMS fail-closed check (F7, round-7 audit).

Tests the pure helper directly so we don't have to boot ``prod`` (whose
SECRET_KEY guard would also fire under the dev settings used by the test run).
"""
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings._sms_guard import validate_twilio_prod_config

_VALID = dict(
    sms_backend="twilio",
    public_base_url="https://cwac.example.com",
    messaging_service_sid="MG" + "a" * 32,
)


class ValidateTwilioProdConfigTest(SimpleTestCase):
    def _validate(self, **overrides):
        kw = dict(_VALID)
        kw.update(overrides)
        validate_twilio_prod_config(**kw)

    def test_non_twilio_backend_skips_check(self):
        # console/locmem never send real SMS -> no requirements.
        self._validate(sms_backend="console")
        self._validate(sms_backend="locmem")

    def test_valid_twilio_config_passes(self):
        self._validate()  # defaults are a valid full config

    def test_missing_base_url_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            self._validate(public_base_url="")

    def test_non_https_base_url_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            self._validate(public_base_url="http://cwac.example.com")

    def test_base_url_without_host_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            self._validate(public_base_url="https://")

    def test_missing_sid_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            self._validate(messaging_service_sid="")

    def test_non_mg_sid_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            self._validate(messaging_service_sid="PN" + "a" * 32)
