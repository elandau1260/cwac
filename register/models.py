"""Models for CWAC owner registrations and their animals.

A :class:`Registration` is one owner's entry into a clinic's pre-registration:
their contact info, the lottery/clinic outcome, a 256-bit self-edit token, the
fire-and-forget result-SMS state, and provenance (public owner vs. staff-added).

:class:`Animal` belongs to a registration. There is deliberately **no** ``weight``
field (FR-8/TC-009).

AnimalID assignment is split into two non-overlapping ranges, DB-enforced:
lottery assigns **1..999**; staff walk-in/admit assigns **>=1000** (a dedicated
sequence on ``Event.next_staff_id``, not counted toward X/Y). The two ranges
together cover every positive integer, so :meth:`Registration.clean` cross-checks
the value against ``id_source`` to prove which allocator produced it.
"""
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Max

#: Lottery AnimalIDs are drawn from this inclusive range (Decision 4).
LOTTERY_ANIMAL_ID_MIN = 1
LOTTERY_ANIMAL_ID_MAX = 999
#: Staff walk-in/admit IDs start at 1000 and count up (not toward X/Y).
STAFF_ANIMAL_ID_MIN = 1000


def generate_edit_token():
    """A fresh 256-bit URL-safe token per registration row.

    A bare ``default=secrets.token_urlsafe`` would be evaluated once at import
    time and reuse one token (collision); this module-level callable is invoked
    per row, so each registration gets its own secret — the only auth for
    self-edit (FR-20).
    """
    return secrets.token_urlsafe(32)


class Registration(models.Model):
    """One owner's pre-registration for a clinic."""

    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        SELECTED = "selected", "Selected"
        WAITLISTED = "waitlisted", "Waitlisted"
        NOT_SELECTED = "not_selected", "Not selected"
        CHECKED_IN = "checked_in", "Checked in"

    class IdSource(models.TextChoices):
        LOTTERY = "lottery", "Lottery"
        STAFF = "staff", "Staff"

    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        SPANISH = "es", "Spanish"

    class ResultSmsState(models.TextChoices):
        # Fire-and-forget result-SMS state for admin/export (Phase 6). ``null``
        # = no attempt; ``sending`` = claimed, in flight; ``sent`` = Twilio
        # accepted (2xx); ``failed`` = synchronous 4xx; ``unknown`` = a *caught*
        # ambiguous outcome (5xx/timeout/connection). A process crash is NOT
        # ``unknown`` — it leaves ``null`` or a persistent ``sending``. Never
        # retried; neither ``null`` nor ``sending`` is ever resent.
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent (accepted)"
        FAILED = "failed", "Failed"
        UNKNOWN = "unknown", "Unknown"

    class CreationSource(models.TextChoices):
        PUBLIC = "public", "Public (owner)"
        STAFF = "staff", "Staff"

    # --- Relationships ------------------------------------------------------
    event = models.ForeignKey(
        "events.Event", related_name="registrations", on_delete=models.CASCADE,
    )
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_registrations",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The staff user that created a staff-source row (null for public).",
    )
    admitted_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="admitted_registrations",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        help_text="The staff user that admitted an existing public row (1000+ ID).",
    )

    # --- AnimalID (allocation-managed; read-only outside the allocators) ----
    # Lottery assigns 1..999; staff walk-in/admit assigns >=1000. Never typed
    # or edited by hand — set only by next_animal_id() / allocate_staff_animal_id().
    animal_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        help_text="Assigned by the lottery (1..999) or staff (>=1000); "
        "read-only outside the allocation services.",
    )
    id_source = models.CharField(
        max_length=10,
        choices=IdSource.choices,
        null=True,
        blank=True,
        editable=False,
        help_text="Which allocator assigned animal_id (set together with it).",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REGISTERED,
    )
    edit_token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        default=generate_edit_token,
    )
    language = models.CharField(
        max_length=2, choices=Language.choices, default=Language.ENGLISH,
    )

    # --- Clinic-day state ---------------------------------------------------
    printed_at = models.DateTimeField(null=True, blank=True, editable=False)
    checked_in_at = models.DateTimeField(null=True, blank=True, editable=False)

    # --- Fire-and-forget result-SMS state (Phase 6) -------------------------
    result_sms_state = models.CharField(
        max_length=10,
        choices=ResultSmsState.choices,
        null=True,
        blank=True,
        default=None,
        editable=False,
    )
    result_sms_sent_at = models.DateTimeField(null=True, blank=True, editable=False)

    # --- Application-level SMS consent (the only app-side SMS gate) ---------
    # True => signup + result SMS are skipped; status still shows on the
    # edit-link page (FR-42). Provider-side STOP/START is not mirrored.
    sms_opt_out = models.BooleanField(default=False)

    # --- Owner contact info (all required) ---------------------------------
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(
        max_length=20, help_text="E.164 (Phase 3 validates + normalizes)."
    )
    email = models.EmailField()
    address = models.CharField(max_length=300)

    # --- Provenance ---------------------------------------------------------
    creation_source = models.CharField(
        max_length=10,
        choices=CreationSource.choices,
        default=CreationSource.PUBLIC,
    )
    admitted_at = models.DateTimeField(null=True, blank=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event", "last_name", "first_name"]
        constraints = [
            # Lottery/staff IDs are unique per event. Multiple NULLs are allowed
            # (registrations before the lottery have no ID yet). This is the
            # Postgres partial unique index from the plan; on SQLite it behaves
            # the same way (NULLs excluded by the condition).
            models.UniqueConstraint(
                fields=["event", "animal_id"],
                condition=models.Q(animal_id__isnull=False),
                name="unique_animal_id_per_event",
            ),
        ]

    def __str__(self):
        tag = f"#{self.animal_id}" if self.animal_id else "—"
        return f"{tag} {self.first_name} {self.last_name} ({self.event})"

    def clean(self):
        """Cross-check ``animal_id`` range against ``id_source``.

        Lottery ⇒ 1..999; staff ⇒ >=1000. Since ``1..999 ∪ >=1000`` covers every
        positive integer, the range alone cannot prove the allocator, so both
        must agree (the partial unique index guarantees event-uniqueness).
        """
        super().clean()
        if self.animal_id is not None:
            if self.id_source == self.IdSource.LOTTERY:
                if not (LOTTERY_ANIMAL_ID_MIN <= self.animal_id <= LOTTERY_ANIMAL_ID_MAX):
                    raise ValidationError(
                        {"animal_id": "Lottery IDs must be in 1..999."}
                    )
            elif self.id_source == self.IdSource.STAFF:
                if self.animal_id < STAFF_ANIMAL_ID_MIN:
                    raise ValidationError(
                        {"animal_id": "Staff IDs must be >= 1000."}
                    )
            elif self.id_source is None:
                raise ValidationError(
                    {"id_source": "An animal_id requires an id_source."}
                )
        elif self.id_source is not None:
            raise ValidationError(
                {"id_source": "id_source is set but animal_id is not."}
            )

    @property
    def is_attended(self):
        """Authoritative 'showed up' signal: printed (FR-35/TC-043)."""
        return self.printed_at is not None

    # --- Allocation services ------------------------------------------------
    @classmethod
    def next_animal_id(cls, event):
        """Next lottery AnimalID = (max existing ID in the **1..999 lottery
        range**) + 1, else 1.

        Staff IDs (>=1000) are deliberately excluded so a staff-grown row can
        never inflate the lottery sequence. Used by the lottery only (Phase 5).
        """
        agg = cls.objects.filter(
            event=event,
            animal_id__gte=LOTTERY_ANIMAL_ID_MIN,
            animal_id__lte=LOTTERY_ANIMAL_ID_MAX,
        ).aggregate(max_id=Max("animal_id"))
        return (agg["max_id"] or 0) + 1

    @classmethod
    def allocate_staff_animal_id(cls, event, registration):
        """Assign the next **staff** ID (>=1000) to ``registration``.

        Runs under ``transaction.atomic()`` with the **Event row locked and
        reloaded** (``select_for_update``), so concurrent walk-in/admit calls
        cannot race on ``next_staff_id`` and a deleted highest ID is never
        reused (no ``max()+1``). Sets ``animal_id`` + ``id_source='staff'`` and
        saves both the event counter and the registration. The caller (walk-in
        add / admit, Phase 10) additionally sets ``status='selected'``.
        """
        if event.pk is None:
            raise ValueError("Cannot allocate a staff ID against an unsaved event")

        with transaction.atomic():
            # Lock + reload the Event row through its own manager (avoids a
            # circular import of events.models at module load time).
            locked_event = (
                type(event).objects.select_for_update().get(pk=event.pk)
            )
            next_id = locked_event.next_staff_id
            registration.animal_id = next_id
            registration.id_source = cls.IdSource.STAFF
            locked_event.next_staff_id = next_id + 1
            locked_event.save(update_fields=["next_staff_id"])
            registration.save()
            # Reflect the incremented counter on the passed-in instance.
            event.next_staff_id = locked_event.next_staff_id
        return registration


class Animal(models.Model):
    """One animal belonging to a registration."""

    class Sex(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"
        MALE_NEUTERED = "MN", "Male-Neutered"
        FEMALE_SPAYED = "FS", "Female-Spayed"

    registration = models.ForeignKey(
        Registration, related_name="animals", on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=100)
    species = models.CharField(max_length=100)
    age = models.CharField(
        max_length=30, help_text="Free text, e.g. '3 years' or '8 months'."
    )
    breed = models.CharField(max_length=100, blank=True, default="")
    color = models.CharField(max_length=100, blank=True, default="")
    sex = models.CharField(
        max_length=2, choices=Sex.choices, blank=True, default="",
    )
    services_requested = models.JSONField(default=list)
    last_vaccinated_date = models.DateField(null=True, blank=True)
    medical_concern = models.TextField(blank=True, default="")
    # NOTE: deliberately no ``weight`` field (FR-8/TC-009).

    class Meta:
        # Stable print grouping (labels group animals in id order).
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.species})" if self.name else self.species
