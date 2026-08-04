"""Phase 2 event-admin, generated-slug, flyer, QR, and deletion tests."""

from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, models
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import User
from events.admin import EventAdmin
from events.models import Event
from events.services_qr import qr_jpeg
from events.tests import make_event
from register.models import Animal, Registration


UserModel = get_user_model()


class EventGeneratedSlugTest(TestCase):
    """FR-2 / TC-002: omitted slugs are generated and remain unique."""

    def test_generates_slug_from_name(self):
        event = make_event(name="Oakland Community Clinic", slug="")
        self.assertEqual(event.slug, "oakland-community-clinic")

    def test_collision_uses_next_numeric_suffix(self):
        first = make_event(name="Oakland Clinic", slug="")
        second = make_event(name="Oakland Clinic", slug="")
        third = make_event(name="Oakland Clinic", slug="")
        self.assertEqual(first.slug, "oakland-clinic")
        self.assertEqual(second.slug, "oakland-clinic-2")
        self.assertEqual(third.slug, "oakland-clinic-3")

    def test_generated_slug_respects_field_length_with_suffix(self):
        first = make_event(name="A" * 100, slug="")
        second = make_event(name="A" * 100, slug="")
        self.assertEqual(len(first.slug), 40)
        self.assertEqual(len(second.slug), 40)
        self.assertTrue(second.slug.endswith("-2"))

    def test_non_slugifiable_name_gets_safe_fallback(self):
        event = make_event(name="***", slug="")
        self.assertEqual(event.slug, "event")

    def test_explicit_slug_is_preserved(self):
        event = make_event(name="Oakland Clinic", slug="custom-code")
        self.assertEqual(event.slug, "custom-code")

    def test_insert_race_retries_with_next_suffix(self):
        """A concurrent winner between exists() and INSERT gets ``-2``."""
        now = timezone.now()
        event = Event(
            name="Race Clinic",
            date=now.date(),
            open_at=now - timedelta(hours=1),
            close_at=now + timedelta(hours=1),
            x_seen=1,
            y_waitlist=1,
            z_applicants=1,
        )
        original_save = models.Model.save
        save_calls = 0

        def collide_once(instance, *args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                raise IntegrityError("simulated concurrent slug insert")
            return original_save(instance, *args, **kwargs)

        # exists(): candidate initially free; after INSERT failure the winning
        # row is visible; suffixed candidate is free.
        with (
            patch.object(Event.objects, "filter") as filtered,
            patch.object(models.Model, "save", new=collide_once),
        ):
            filtered.return_value.exists.side_effect = [False, True, False]
            event.save()

        self.assertEqual(event.slug, "race-clinic-2")
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())


class EventAdminPhase2Test(TestCase):
    """FR-1/30: full event configuration is Admin-only."""

    def setUp(self):
        self.admin_user = UserModel.objects.create_superuser(
            "admin", "admin@example.com", "sup3rs3cret!"
        )
        self.volunteer = UserModel.objects.create_user(
            "volunteer", "volunteer@example.com", "sup3rs3cret!"
        )
        self.client.force_login(self.admin_user)

    def test_admin_creates_fully_configured_draft_with_generated_slug(self):
        response = self.client.post(
            reverse("admin:events_event_add"),
            {
                "slug": "",
                "name": "September Community Clinic",
                "description": "A neighborhood clinic.",
                "date": "2026-09-12",
                "location": "Oakland Animal Services",
                "timezone": "America/Los_Angeles",
                "open_at_0": "2026-09-01",
                "open_at_1": "09:00:00",
                "close_at_0": "2026-09-10",
                "close_at_1": "17:00:00",
                "x_seen": "80",
                "y_waitlist": "20",
                "z_applicants": "150",
                "offers_flea_deworming": "on",
                "offers_microchip": "on",
                "offers_vaccination": "on",
                "offers_vet": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302, response.context)

        event = Event.objects.get(name="September Community Clinic")
        self.assertEqual(event.slug, "september-community-clinic")
        self.assertEqual(event.status, Event.Status.DRAFT)
        self.assertEqual(event.location, "Oakland Animal Services")
        self.assertEqual((event.x_seen, event.y_waitlist, event.z_applicants), (80, 20, 150))
        self.assertTrue(all(event.services_offered.values()))

    def test_event_model_admin_explicitly_denies_volunteer_permissions(self):
        model_admin = EventAdmin(Event, admin.site)
        request = RequestFactory().get("/admin/events/event/")
        request.user = self.volunteer

        self.assertFalse(model_admin.has_module_permission(request))
        self.assertFalse(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))


class EventFlyerAndQrTest(TestCase):
    """FR-3 / TC-003: flyer URL plus a downloadable QR-code JPG."""

    def setUp(self):
        self.admin_user = UserModel.objects.create_superuser(
            "admin", "admin@example.com", "sup3rs3cret!"
        )
        self.event = make_event(name="QR Clinic", slug="qr-clinic")
        self.client.force_login(self.admin_user)

    def test_flyer_shows_absolute_signup_url_and_download(self):
        response = self.client.get(
            reverse("events:flyer", kwargs={"pk": self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "http://testserver/r/qr-clinic/")
        self.assertContains(response, "Download QR JPG")

    def test_qr_download_is_a_valid_jpeg(self):
        url = reverse("events:qr_download", kwargs={"pk": self.event.pk})
        response = self.client.get(f"{url}?download=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="qr-clinic-signup-qr.jpg"',
        )
        with Image.open(BytesIO(response.content)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.width, image.height)

    @patch("events.views.qr_jpeg", return_value=b"jpeg")
    def test_qr_payload_is_exact_signup_url(self, render_qr):
        self.client.get(reverse("events:qr_download", kwargs={"pk": self.event.pk}))
        render_qr.assert_called_once_with("http://testserver/r/qr-clinic/")

    def test_qr_service_returns_jpeg_bytes(self):
        image_bytes = qr_jpeg("https://example.com/r/qr-clinic/")
        self.assertTrue(image_bytes.startswith(b"\xff\xd8"))
        self.assertTrue(image_bytes.endswith(b"\xff\xd9"))

    def test_change_page_links_to_flyer(self):
        response = self.client.get(
            reverse("admin:events_event_change", args=[self.event.pk])
        )
        self.assertContains(
            response,
            reverse("events:flyer", kwargs={"pk": self.event.pk}),
        )


class EventCascadeDeleteTest(TestCase):
    """FR-39 / TC-048: explicit warning, cascade, unrelated data retained."""

    def setUp(self):
        self.admin_user = UserModel.objects.create_superuser(
            "admin", "admin@example.com", "sup3rs3cret!"
        )
        self.client.force_login(self.admin_user)
        self.event = make_event(name="Delete Me", slug="delete-me")
        self.other_event = make_event(name="Keep Me", slug="keep-me")
        self.registration = Registration.objects.create(
            event=self.event,
            first_name="Ada",
            last_name="Lovelace",
            phone="+15105550100",
            email="ada@example.com",
            address="1 Clinic St",
        )
        self.animal = Animal.objects.create(
            registration=self.registration,
            name="Pixel",
            species="Cat",
            age="3 years",
        )
        self.delete_url = reverse("admin:events_event_delete", args=[self.event.pk])

    def test_confirmation_warns_about_registration_and_animal_deletion(self):
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "permanently deletes all of its registrations and animals")

    def test_confirmed_delete_cascades_without_touching_other_events(self):
        response = self.client.post(self.delete_url, {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Event.objects.filter(pk=self.event.pk).exists())
        self.assertFalse(Registration.objects.filter(pk=self.registration.pk).exists())
        self.assertFalse(Animal.objects.filter(pk=self.animal.pk).exists())
        self.assertTrue(Event.objects.filter(pk=self.other_event.pk).exists())
