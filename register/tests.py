"""Phase 1 model tests for Registration and Animal.

Covers:
- TC-009: no 'weight' field on Animal; per-animal fields present.
- TC-014/015 (model layer): next_animal_id (1..999 only, ignores 1000+ staff IDs)
  and allocate_staff_animal_id (>=1000 sequence, counter increment).
- Registration.clean() range<->id_source cross-check.
- Partial unique index: (event, animal_id) unique when not null; multiple NULLs
  allowed; same ID across different events allowed.
- Defaults, edit_token uniqueness, is_attended.
"""
import zoneinfo
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from events.models import Event
from register.models import (
    Animal,
    Registration,
    generate_edit_token,
)


def make_event(**overrides):
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


def make_registration(event, **overrides):
    defaults = dict(
        event=event,
        first_name="Ada",
        last_name="Lovelace",
        phone="+15105550100",
        email="ada@example.com",
        address="1 Clinic St",
    )
    defaults.update(overrides)
    return Registration.objects.create(**defaults)


class AnimalFieldsTest(TestCase):
    """TC-009: per-animal fields, and NO weight field anywhere."""

    def test_has_no_weight_field(self):
        names = {f.name for f in Animal._meta.get_fields()}
        self.assertNotIn("weight", names)

    def test_has_expected_fields(self):
        names = {f.name for f in Animal._meta.get_fields()}
        for expected in (
            "name", "species", "age", "breed", "color", "sex",
            "services_requested", "last_vaccinated_date", "medical_concern",
            "registration",
        ):
            self.assertIn(expected, names)

    def test_sex_choices_match_export_spec(self):
        choices = {value for value, _label in Animal.Sex.choices}
        self.assertEqual(choices, {"M", "F", "MN", "FS"})


class RegistrationDefaultsTest(TestCase):
    def test_defaults_for_a_public_signup(self):
        r = make_registration(make_event())
        self.assertEqual(r.status, Registration.Status.REGISTERED)
        self.assertEqual(r.language, Registration.Language.ENGLISH)
        self.assertEqual(r.creation_source, Registration.CreationSource.PUBLIC)
        self.assertFalse(r.sms_opt_out)
        self.assertIsNone(r.animal_id)
        self.assertIsNone(r.id_source)
        self.assertIsNone(r.result_sms_state)
        self.assertFalse(r.is_attended)

    def test_next_staff_id_defaults_to_1000(self):
        e = make_event()
        self.assertEqual(e.next_staff_id, 1000)


class RegistrationCleanTest(TestCase):
    """clean() cross-checks animal_id range against id_source."""

    def _build(self, event=None, **overrides):
        defaults = dict(
            event=event or make_event(),
            first_name="A", last_name="B", phone="+1",
            email="a@b.com", address="x",
        )
        defaults.update(overrides)
        return Registration(**defaults)  # unsaved -> clean() in isolation

    def test_lottery_id_in_range_ok(self):
        e = make_event()
        self._build(e, animal_id=1, id_source="lottery").full_clean()
        self._build(e, animal_id=999, id_source="lottery").full_clean()

    def test_lottery_id_above_999_rejected(self):
        with self.assertRaises(ValidationError):
            self._build(animal_id=1000, id_source="lottery").full_clean()

    def test_staff_id_ok(self):
        e = make_event()
        self._build(e, animal_id=1000, id_source="staff").full_clean()
        self._build(e, animal_id=1234, id_source="staff").full_clean()

    def test_staff_id_below_1000_rejected(self):
        with self.assertRaises(ValidationError):
            self._build(animal_id=500, id_source="staff").full_clean()

    def test_id_without_source_rejected(self):
        with self.assertRaises(ValidationError):
            self._build(animal_id=5).full_clean()

    def test_source_without_id_rejected(self):
        with self.assertRaises(ValidationError):
            self._build(id_source="lottery").full_clean()

    def test_no_id_no_source_ok(self):
        self._build().full_clean()


class RegistrationNextAnimalIdTest(TestCase):
    """Lottery sequence = max(1..999 IDs)+1, ignoring staff IDs (>=1000)."""

    def test_empty_event_returns_1(self):
        self.assertEqual(Registration.next_animal_id(make_event()), 1)

    def test_ignores_staff_ids(self):
        e = make_event()
        make_registration(e, animal_id=1000, id_source="staff")
        make_registration(e, animal_id=1042, id_source="staff")
        self.assertEqual(Registration.next_animal_id(e), 1)

    def test_max_lottery_id_plus_one(self):
        e = make_event()
        make_registration(e, animal_id=5, id_source="lottery")
        make_registration(e, animal_id=1000, id_source="staff")  # ignored
        self.assertEqual(Registration.next_animal_id(e), 6)

    def test_boundary_at_999(self):
        # next_animal_id reports the next number; the lottery (Phase 5) guards
        # the >999 case. Here it simply returns 1000 once 999 is taken.
        e = make_event()
        make_registration(e, animal_id=999, id_source="lottery")
        self.assertEqual(Registration.next_animal_id(e), 1000)


class RegistrationAllocateStaffAnimalIdTest(TestCase):
    """Staff IDs come from Event.next_staff_id (>=1000), atomic & monotonic."""

    def test_assigns_first_staff_id(self):
        e = make_event()
        r = make_registration(e)
        Registration.allocate_staff_animal_id(e, r)
        self.assertEqual(r.animal_id, 1000)
        self.assertEqual(r.id_source, Registration.IdSource.STAFF)

    def test_increments_counter_on_event(self):
        e = make_event()
        r = make_registration(e)
        Registration.allocate_staff_animal_id(e, r)
        e.refresh_from_db()
        self.assertEqual(e.next_staff_id, 1001)

    def test_passed_event_instance_reflects_new_counter(self):
        e = make_event()
        r = make_registration(e)
        Registration.allocate_staff_animal_id(e, r)
        self.assertEqual(e.next_staff_id, 1001)

    def test_sequence_is_monotonic_and_unique(self):
        e = make_event()
        r1 = make_registration(e)
        r2 = make_registration(e)
        r3 = make_registration(e)
        for r in (r1, r2, r3):
            Registration.allocate_staff_animal_id(e, r)
        ids = {r1.animal_id, r2.animal_id, r3.animal_id}
        self.assertEqual(ids, {1000, 1001, 1002})

    def test_staff_id_not_in_lottery_range(self):
        e = make_event()
        r = make_registration(e)
        Registration.allocate_staff_animal_id(e, r)
        # Staff IDs do not inflate the lottery sequence.
        self.assertEqual(Registration.next_animal_id(e), 1)


class RegistrationEditTokenTest(TestCase):
    def test_generate_edit_token_is_random_per_call(self):
        tokens = {generate_edit_token() for _ in range(50)}
        self.assertEqual(len(tokens), 50)

    def test_each_registration_gets_a_distinct_token(self):
        e = make_event()
        r1 = make_registration(e)
        r2 = make_registration(e)
        self.assertTrue(r1.edit_token)
        self.assertNotEqual(r1.edit_token, r2.edit_token)

    def test_edit_token_unique_constraint(self):
        e = make_event()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Registration.objects.create(
                    event=e, first_name="A", last_name="B", phone="+1",
                    email="a@b.com", address="x", edit_token="same-token",
                )
                Registration.objects.create(
                    event=e, first_name="C", last_name="D", phone="+2",
                    email="c@d.com", address="y", edit_token="same-token",
                )


class RegistrationIsAttendedTest(TestCase):
    def test_not_attended_until_printed(self):
        r = make_registration(make_event())
        self.assertFalse(r.is_attended)

    def test_attended_after_printed(self):
        r = make_registration(make_event())
        r.printed_at = timezone.now()
        r.save(update_fields=["printed_at"])
        self.assertTrue(r.is_attended)


class RegistrationPartialUniqueIndexTest(TestCase):
    def test_duplicate_event_animal_id_rejected(self):
        e = make_event()
        make_registration(e, animal_id=7, id_source="lottery")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_registration(e, animal_id=7, id_source="lottery")

    def test_multiple_null_animal_ids_allowed(self):
        e = make_event()
        make_registration(e)
        make_registration(e)  # both animal_id NULL -> allowed
        self.assertEqual(Registration.objects.filter(event=e).count(), 2)

    def test_same_id_in_different_events_allowed(self):
        e1 = make_event(slug="event-one")
        e2 = make_event(slug="event-two")
        make_registration(e1, animal_id=7, id_source="lottery")
        make_registration(e2, animal_id=7, id_source="lottery")  # OK
        self.assertEqual(Registration.objects.filter(animal_id=7).count(), 2)
