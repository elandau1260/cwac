"""Phase 1 model tests for events.

Covers:
- TC-002: slug uniqueness (duplicate rejected).
- TC-047 (deterministic part): at_capacity at Z, below at Z-1.
- TC-058: forward-only lifecycle (transition rejects backward/skip/no-op;
  status editable=False; signup_open stays False once lottery_run_at is set).
- FR-4: read-time window gating (draft closed even in window; live within window
  open; before/after closed; lottery_run_at defense-in-depth).
- FR-34: owner_can_add / owner_can_edit.
- Helper coverage: services_offered, auto_run_deadline.
- EventAdminForm: open_at/close_at entered/shown in the event timezone.

The select_for_update() inside transition() is a no-op on the SQLite test DB, so
the concurrency guarantees (true row locking) need PostgreSQL (TC-058 note);
the forward-only *logic* is fully testable here.
"""
import datetime
import zoneinfo
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from events.admin import EventAdminForm
from events.models import Event, InvalidTransition


def make_event(**overrides):
    """A live-by-default event with a sign-up window around 'now'."""
    now = timezone.now()
    defaults = dict(
        slug="test-event",
        name="Test Clinic",
        date=now.date(),
        timezone=zoneinfo.ZoneInfo("America/Los_Angeles"),
        open_at=now - timedelta(hours=1),
        close_at=now + timedelta(hours=1),
        x_seen=10,
        y_waitlist=5,
        z_applicants=50,
    )
    defaults.update(overrides)
    return Event.objects.create(**defaults)


def _make_reg(event):
    """Minimal Registration (imported lazily to avoid a cross-app top import)."""
    from register.models import Registration

    return Registration.objects.create(
        event=event,
        first_name="Ada",
        last_name="Lovelace",
        phone="+15105550100",
        email="ada@example.com",
        address="1 Clinic St",
    )


class EventServicesOfferedTest(TestCase):
    def test_services_offered_maps_all_four_flags(self):
        e = make_event(
            offers_vaccination=True,
            offers_vet=True,
            offers_flea_deworming=False,
            offers_microchip=False,
        )
        offered = e.services_offered
        self.assertEqual(
            set(offered),
            {"flea_deworming", "microchip", "vaccination", "vet"},
        )
        self.assertTrue(offered["vaccination"])
        self.assertTrue(offered["vet"])
        self.assertFalse(offered["flea_deworming"])
        self.assertFalse(offered["microchip"])


class EventTransitionTest(TestCase):
    """TC-058: the lifecycle is forward-only and atomic via transition()."""

    def test_status_field_is_not_editable(self):
        self.assertFalse(Event._meta.get_field("status").editable)

    def test_valid_one_step_forward_succeeds(self):
        e = make_event()
        e.transition(Event.Status.LIVE)
        self.assertEqual(e.status, Event.Status.LIVE)

    def test_full_forward_chain(self):
        e = make_event()
        for target in (
            Event.Status.LIVE,
            Event.Status.LOTTERY_RUN,
            Event.Status.ACTIVE,
            Event.Status.COMPLETED,
        ):
            e.transition(target)
        self.assertEqual(e.status, Event.Status.COMPLETED)

    def test_skip_move_rejected(self):
        e = make_event()  # draft
        with self.assertRaises(InvalidTransition):
            e.transition(Event.Status.ACTIVE)  # draft -> active skips 'live'

    def test_backward_move_rejected(self):
        e = make_event()
        e.transition(Event.Status.LIVE)
        e.transition(Event.Status.LOTTERY_RUN)
        with self.assertRaises(InvalidTransition):
            e.transition(Event.Status.LIVE)  # cannot reopen signups

    def test_noop_move_rejected(self):
        e = make_event(status=Event.Status.LIVE)
        with self.assertRaises(InvalidTransition):
            e.transition(Event.Status.LIVE)

    def test_unknown_target_rejected(self):
        e = make_event()
        with self.assertRaises(InvalidTransition):
            e.transition("frozen")

    def test_transition_persists_to_db(self):
        e = make_event()
        e.transition(Event.Status.LIVE)
        self.assertEqual(Event.objects.get(pk=e.pk).status, Event.Status.LIVE)


class EventSignupOpenTest(TestCase):
    """FR-4 / TC-058: read-time window gating + lottery_run_at guard."""

    def test_draft_event_closed_even_within_window(self):
        e = make_event()  # status defaults to draft
        self.assertFalse(e.signup_open())

    def test_live_event_within_window_open(self):
        e = make_event(status=Event.Status.LIVE)
        self.assertTrue(e.signup_open())

    def test_live_before_window_closed(self):
        now = timezone.now()
        e = make_event(
            status=Event.Status.LIVE,
            open_at=now + timedelta(hours=1),
            close_at=now + timedelta(hours=2),
        )
        self.assertFalse(e.signup_open(now=now))

    def test_live_after_window_closed(self):
        now = timezone.now()
        e = make_event(
            status=Event.Status.LIVE,
            open_at=now - timedelta(hours=2),
            close_at=now - timedelta(hours=1),
        )
        self.assertFalse(e.signup_open(now=now))

    def test_window_is_half_open_close_excluded(self):
        # [open_at, close_at) — exactly at close_at is closed.
        now = timezone.now()
        e = make_event(status=Event.Status.LIVE, open_at=now - timedelta(hours=1))
        e.close_at = now
        e.save(update_fields=["close_at"])
        self.assertFalse(e.signup_open(now=now))

    def test_lottery_run_at_is_defense_in_depth(self):
        # TC-058: signup_open is False once lottery_run_at is set, even though
        # the event is live and within its window.
        e = make_event(status=Event.Status.LIVE, lottery_run_at=timezone.now())
        self.assertTrue(e.is_published())
        self.assertTrue(e.open_at <= timezone.now() < e.close_at)
        self.assertFalse(e.signup_open())

    def test_reopening_close_at_after_lottery_does_not_reopen_signups(self):
        now = timezone.now()
        e = make_event(
            status=Event.Status.LIVE,
            open_at=now - timedelta(hours=2),
            close_at=now - timedelta(hours=1),  # already closed
            lottery_run_at=now - timedelta(minutes=30),
        )
        # Admin pushes close_at into the future...
        e.close_at = now + timedelta(hours=1)
        e.save(update_fields=["close_at"])
        self.assertTrue(e.open_at <= now < e.close_at)  # window now 'open'
        self.assertFalse(e.signup_open())  # ...but the lottery already ran


class EventAtCapacityTest(TestCase):
    """TC-047 (deterministic part): at_capacity() at the Z boundary."""

    def test_below_cap_not_full(self):
        e = make_event(z_applicants=3)
        _make_reg(e)
        _make_reg(e)
        self.assertEqual(e.registrations.count(), 2)
        self.assertFalse(e.at_capacity())

    def test_at_cap_full(self):
        e = make_event(z_applicants=2)
        _make_reg(e)
        _make_reg(e)
        self.assertTrue(e.at_capacity())


class EventAutoRunDeadlineTest(TestCase):
    def test_noon_day_after_close_in_event_timezone(self):
        # close_at 2026-08-14 23:00 UTC. America/Los_Angeles is PDT (UTC-7) in
        # August, so local close = 2026-08-14 16:00 PDT; day after = Sat
        # 2026-08-15; noon local = 12:00 PDT = 19:00 UTC.
        utc = datetime.timezone.utc
        e = make_event(
            timezone=zoneinfo.ZoneInfo("America/Los_Angeles"),
            close_at=datetime.datetime(2026, 8, 14, 23, 0, tzinfo=utc),
        )
        deadline = e.auto_run_deadline()
        self.assertEqual(
            deadline.astimezone(utc),
            datetime.datetime(2026, 8, 15, 19, 0, tzinfo=utc),
        )

    def test_no_deadline_without_close_at(self):
        e = Event(name="x", slug="x", date=datetime.date(2026, 1, 1))
        self.assertIsNone(e.auto_run_deadline())


class EventOwnerGatingTest(TestCase):
    """FR-34: owner_can_add / owner_can_edit vs. window & check-in."""

    def _reg(self, event, status="registered"):
        from register.models import Registration

        return Registration.objects.create(
            event=event,
            first_name="A", last_name="B", phone="+1",
            email="a@b.com", address="x", status=status,
        )

    def test_can_add_while_open(self):
        e = make_event(status=Event.Status.LIVE)
        self.assertTrue(e.owner_can_add(self._reg(e)))

    def test_cannot_add_after_close(self):
        now = timezone.now()
        e = make_event(
            status=Event.Status.LIVE,
            open_at=now - timedelta(hours=2),
            close_at=now - timedelta(hours=1),
        )
        self.assertFalse(e.owner_can_add(self._reg(e)))

    def test_cannot_add_checked_in_row(self):
        e = make_event(status=Event.Status.LIVE)
        self.assertFalse(e.owner_can_add(self._reg(e, status="checked_in")))

    def test_can_edit_while_live(self):
        e = make_event(status=Event.Status.LIVE)
        self.assertTrue(e.owner_can_edit(self._reg(e)))

    def test_cannot_edit_after_event_completed(self):
        e = make_event(status=Event.Status.COMPLETED)
        self.assertFalse(e.owner_can_edit(self._reg(e)))

    def test_cannot_edit_checked_in_row(self):
        e = make_event(status=Event.Status.LIVE)
        self.assertFalse(e.owner_can_edit(self._reg(e, status="checked_in")))


class EventSlugUniqueTest(TestCase):
    """TC-002: duplicate slug is rejected (model layer)."""

    def test_duplicate_slug_rejected(self):
        make_event(slug="dupe")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_event(slug="dupe")


class EventAdminRenderSmokeTest(TestCase):
    """The custom form + fieldsets + readonly fields render on the real admin
    add/change pages (catches misconfig the system check does not)."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.admin = get_user_model().objects.create_superuser(
            "admin", "admin@example.com", "sup3rs3cret!"
        )
        self.client.force_login(self.admin)

    def test_add_page_renders(self):
        resp = self.client.get("/admin/events/event/add/")
        self.assertEqual(resp.status_code, 200)

    def test_change_page_renders_with_local_times(self):
        e = make_event(status=Event.Status.LIVE)
        resp = self.client.get(f"/admin/events/event/{e.pk}/change/")
        self.assertEqual(resp.status_code, 200)


class EventAdminFormTimezoneTest(TestCase):
    """The custom admin form enters/displays open_at & close_at in the event's
    own timezone while storing them as UTC."""

    _form_data = dict(
        slug="tz-event",
        name="TZ Clinic",
        date="2026-08-10",
        timezone="America/Los_Angeles",
        open_at="2026-08-10 09:00",
        close_at="2026-08-10 17:00",
        x_seen="10",
        y_waitlist="5",
        z_applicants="50",
    )

    def test_local_times_stored_as_utc(self):
        # 09:00 PDT (UTC-7 in August) == 16:00 UTC; 17:00 PDT == 00:00 next day.
        form = EventAdminForm(data=dict(self._form_data))
        self.assertTrue(form.is_valid(), form.errors)
        event = form.save()
        utc = datetime.timezone.utc
        self.assertEqual(
            event.open_at.astimezone(utc),
            datetime.datetime(2026, 8, 10, 16, 0, tzinfo=utc),
        )
        self.assertEqual(
            event.close_at.astimezone(utc),
            datetime.datetime(2026, 8, 11, 0, 0, tzinfo=utc),
        )

    def test_close_before_open_rejected(self):
        data = dict(self._form_data)
        data["open_at"] = "2026-08-10 18:00"
        data["close_at"] = "2026-08-10 09:00"
        form = EventAdminForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors or form.errors)

    def test_stored_utc_shown_as_local_on_load(self):
        utc = datetime.timezone.utc
        e = Event.objects.create(
            slug="tz-load",
            name="TZ Load",
            date=datetime.date(2026, 8, 10),
            timezone=zoneinfo.ZoneInfo("America/Los_Angeles"),
            open_at=datetime.datetime(2026, 8, 10, 16, 0, tzinfo=utc),  # 09:00 LA
            close_at=datetime.datetime(2026, 8, 11, 0, 0, tzinfo=utc),  # 17:00 LA
            x_seen=1,
            y_waitlist=1,
            z_applicants=1,
        )
        form = EventAdminForm(instance=e)
        # Naive local wall-clock times (what the admin sees/edits).
        self.assertEqual(form.initial["open_at"], datetime.datetime(2026, 8, 10, 9, 0))
        self.assertEqual(form.initial["close_at"], datetime.datetime(2026, 8, 10, 17, 0))
