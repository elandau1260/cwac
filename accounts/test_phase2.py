"""Phase 2 staff-authentication and Admin-role access tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from events.tests import make_event


User = get_user_model()


class StaffAuthenticationTest(TestCase):
    """FR-30 / TC-033, TC-035: username/password session auth."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            "admin", "admin@example.com", "sup3rs3cret!"
        )
        self.volunteer = User.objects.create_user(
            "volunteer", "volunteer@example.com", "sup3rs3cret!"
        )

    def test_login_page_renders(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff login")

    def test_correct_credentials_create_session(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "admin", "password": "sup3rs3cret!"},
        )
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.admin.pk)

    def test_volunteer_credentials_also_create_session(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "volunteer", "password": "sup3rs3cret!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.volunteer.pk)

    def test_wrong_credentials_are_denied(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "admin", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "did not match")

    def test_logout_ends_session(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(
            response, reverse("accounts:login"), fetch_redirect_response=False
        )
        self.assertNotIn("_auth_user_id", self.client.session)


class AdminRoleGateTest(TestCase):
    """Decision 16: event-management helpers are Admin-only."""

    def setUp(self):
        self.event = make_event(slug="role-gate")
        self.admin = User.objects.create_superuser(
            "admin", "admin@example.com", "sup3rs3cret!"
        )
        self.volunteer = User.objects.create_user(
            "volunteer", "volunteer@example.com", "sup3rs3cret!"
        )
        self.flyer_url = reverse("events:flyer", kwargs={"pk": self.event.pk})

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.flyer_url)
        expected = f'{reverse("accounts:login")}?next={self.flyer_url}'
        self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_volunteer_is_forbidden(self):
        self.client.force_login(self.volunteer)
        response = self.client.get(self.flyer_url)
        self.assertEqual(response.status_code, 403)

    def test_admin_is_allowed(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.flyer_url)
        self.assertEqual(response.status_code, 200)
