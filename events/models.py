"""Models for CWAC events (clinics).

An :class:`Event` is a single clinic: its schedule, capacity caps, the services
it offers, and a forward-only lifecycle (``draft → live → lottery_run → active →
completed``). The open/closed state an owner experiences is **computed** from
``open_at``/``close_at`` plus the ``live`` stage (see :meth:`Event.signup_open`),
never stored as a boolean — so the admin always sees reality with no cron and no
manual lock (Decision 8 / R-3).

Phase 1 (this file): the model, the read-time window helpers, the soft applicant
cap ``z_applicants``, the per-event ``timezone`` (IANA), the noon day-after-close
:meth:`auto_run_deadline`, and the atomic forward-only :meth:`transition`. The
custom admin form that edits ``open_at``/``close_at`` in the event's timezone
lives in ``events/admin.py``.
"""
import datetime
import logging

from django.db import models, transaction
from django.utils import timezone

from timezone_field import TimeZoneField

logger = logging.getLogger(__name__)


class InvalidTransition(Exception):
    """Raised by :meth:`Event.transition` for any move that is not exactly one
    forward step (a backward move, a skip, or a no-op).

    The lifecycle is forward-only and read-only outside ``transition()``: once
    an event has reached ``lottery_run``/``completed`` it cannot be regressed to
    ``live`` to reopen signups or re-enable mutations (FR-4 / TC-058).
    """


class Event(models.Model):
    """A single clinic.

    Capacity caps: **X** = animals seen, **Y** = waitlist animals, **Z** = soft
    applicant cap (target max registrations) — all admin-configured per event.
    A small overshoot of Z under concurrent signups is acceptable (R-10); the
    check + insert are deliberately not serialized.
    """

    class Status(models.TextChoices):
        # Order matters: ``transition()`` only allows advancing exactly one step
        # down this list (draft → live → lottery_run → active → completed).
        DRAFT = "draft", "Draft"
        LIVE = "live", "Live"
        LOTTERY_RUN = "lottery_run", "Lottery run"
        ACTIVE = "active", "Active (clinic day)"
        COMPLETED = "completed", "Completed"

    # --- Identification -----------------------------------------------------
    slug = models.SlugField(
        max_length=40,
        unique=True,
        help_text="Unique URL code for this clinic (e.g. 'oak-aug-2026'). "
        "Phase 2 auto-generates this; in the back office it can be typed.",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    date = models.DateField(help_text="The calendar date of the clinic.")
    location = models.CharField(max_length=200, blank=True, default="")

    # --- Schedule & timezone ------------------------------------------------
    # Stored as UTC (USE_TZ=True); the admin enters and reads them in the
    # event's own ``timezone`` (events/admin.py converts to/from local).
    timezone = TimeZoneField(
        default="America/Los_Angeles",
        help_text="Per-event IANA zone. open_at/close_at are entered and shown "
        "in this zone, and it sets when 'noon' (the auto-lottery deadline) is.",
    )
    open_at = models.DateTimeField(
        db_index=True,
        help_text="Sign-up window opens (stored UTC; edited in the event's tz).",
    )
    close_at = models.DateTimeField(
        db_index=True,
        help_text="Sign-up window closes (stored UTC; edited in the event's tz).",
    )

    # --- Capacity caps (per event) -----------------------------------------
    x_seen = models.PositiveIntegerField(
        help_text="X — number of animals this clinic will see."
    )
    y_waitlist = models.PositiveIntegerField(
        help_text="Y — number of waitlist animals (computed on the remainder "
        "after the selected bucket fills)."
    )
    z_applicants = models.PositiveIntegerField(
        help_text="Z — soft cap on registrations/owners. New signups are "
        "rejected once reached; a small concurrent overshoot is acceptable."
    )

    # --- Services offered (drives the public per-animal form) ---------------
    offers_flea_deworming = models.BooleanField(default=False)
    offers_microchip = models.BooleanField(default=False)
    offers_vaccination = models.BooleanField(default=False)
    offers_vet = models.BooleanField(default=False)

    # --- Lifecycle ----------------------------------------------------------
    # ``status`` is forward-only and read-only outside transition(); the admin
    # form renders it read-only (editable=False) so an Admin cannot regress a
    # completed/lottery_run event to reopen signups (FR-4 / TC-058).
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        editable=False,
    )
    # Durable single-run guard: set once when the lottery runs. NOT a signup
    # gate by itself — signups are time-window + live-status driven — but
    # signup_open() also requires it to be None as defense-in-depth (FR-4).
    lottery_run_at = models.DateTimeField(null=True, blank=True, editable=False)
    # Per-event counter for staff walk-in/admit IDs (>= 1000). Incremented under
    # the Event-row lock by Registration.assign_next_walkin_id. These IDs are
    # NOT counted toward X/Y.
    next_staff_id = models.PositiveIntegerField(default=1000, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "name"]

    def __str__(self):
        return f"{self.name} ({self.date})"

    # --- Services -----------------------------------------------------------
    @property
    def services_offered(self):
        """Map of service key -> whether this clinic offers it.

        The public per-animal form renders one checkbox per offered key
        (Phase 3); ``Animal.services_requested`` stores a subset of the keys
        that are ``True`` here.
        """
        return {
            "flea_deworming": self.offers_flea_deworming,
            "microchip": self.offers_microchip,
            "vaccination": self.offers_vaccination,
            "vet": self.offers_vet,
        }

    # --- Lifecycle ----------------------------------------------------------
    def is_published(self):
        """An event is 'live' (open for business) iff ``status == 'live'``."""
        return self.status == self.Status.LIVE

    def transition(self, target, *, by=None):
        """Advance the event's status by **exactly one forward step**.

        The only way ``status`` changes. Runs inside ``transaction.atomic()``,
        **locks and reloads the Event row** (``select_for_update``), and
        validates a single forward move (``draft→live→lottery_run→active→
        completed``). Any backward move, skip, or no-op raises
        :class:`InvalidTransition`. Used by the Publish/Activate/Complete admin
        actions (Phase 2+) **and** by the lottery's own ``live→lottery_run``
        move (Phase 5), so every transition is atomic and one-step (FR-4/TC-058).

        ``by`` (optional) is the user/system triggering the move, for logging.
        """
        target_value = (
            target.value if isinstance(target, self.Status) else target
        )
        if target_value not in self.Status.values:
            raise InvalidTransition(f"Unknown target status: {target!r}")
        if self.pk is None:
            raise InvalidTransition("Cannot transition an unsaved event")

        with transaction.atomic():
            locked = Event.objects.select_for_update().get(pk=self.pk)
            current = locked.status
            order = self.Status.values  # ['draft','live','lottery_run','active','completed']
            step = order.index(target_value) - order.index(current)
            if step != 1:
                raise InvalidTransition(
                    f"Status may only advance one step at a time "
                    f"({current!r} → {target_value!r}); "
                    f"use the appropriate admin action."
                )
            locked.status = target_value
            locked.save(update_fields=["status"])
            # Reflect the committed row back onto this in-memory instance.
            self.refresh_from_db()
            logger.info(
                "Event %s transitioned %s → %s (by=%s)",
                self.pk, current, target_value, by,
            )
        return self

    # --- Window / signup gating (read-time, no cron) ------------------------
    def signup_open(self, now=None):
        """Signups are accepted iff the event is live, the lottery has not run,
        and ``now`` is within ``[open_at, close_at)`` (FR-4).

        The ``lottery_run_at is None`` term is **defense-in-depth**: even if
        ``status`` were forced back to ``live``, signups stay closed once the
        lottery has run, and reopening ``close_at`` after the lottery cannot
        reopen signups (TC-058).
        """
        if now is None:
            now = timezone.now()
        return (
            self.is_published()
            and self.lottery_run_at is None
            and self.open_at is not None
            and self.close_at is not None
            and self.open_at <= now < self.close_at
        )

    def at_capacity(self):
        """Soft applicant cap reached? (``registrations.count() >= z_applicants``).

        NOT locked: concurrent signups at the boundary may overshoot by a few,
        which is acceptable (R-10/Decision 12). Gates only brand-new
        registrations; an existing owner may still add animals.
        """
        return self.registrations.count() >= self.z_applicants

    def auto_run_deadline(self):
        """Noon (12:00 local) on the calendar day after ``close_at``, in this
        event's timezone — the latest the lottery auto-runs (R-4/FR-40).

        Returns a tz-aware datetime comparable to ``timezone.now()`` (any aware
        datetime compares by instant). ``None`` if ``close_at`` is unset.
        """
        if self.close_at is None or self.timezone is None:
            return None
        local_close = self.close_at.astimezone(self.timezone)
        day_after = local_close.date() + datetime.timedelta(days=1)
        return datetime.datetime.combine(
            day_after, datetime.time(hour=12), tzinfo=self.timezone,
        )

    def owner_can_add(self, reg):
        """An owner may add an animal iff signups are open and the row isn't
        checked in."""
        return self.signup_open() and reg.status != reg.Status.CHECKED_IN

    def owner_can_edit(self, reg):
        """An owner may edit/remove iff the event isn't completed and the row
        isn't checked in. (Add is additionally gated by :meth:`owner_can_add`.)"""
        return (
            self.status != self.Status.COMPLETED
            and reg.status != reg.Status.CHECKED_IN
        )
