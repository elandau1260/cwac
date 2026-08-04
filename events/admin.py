"""Django admin for events (back-office).

The notable piece is :class:`EventAdminForm`: ``open_at``/``close_at`` are stored
as UTC (``USE_TZ=True``) but the admin enters and reads them in the **event's
own timezone**, so the admin always works in local wall-clock time for that
clinic. A naive local input from the split-datetime widget is localized to the
selected timezone on save; on load the stored UTC value is shown in local time.
Wall times that do not exist (the spring-forward gap) or that exist twice (the
fall-back fold) are rejected with a validation error.
"""
import datetime
import zoneinfo

from django import forms
from django.contrib import admin
from django.utils import timezone

from .models import Event

#: Fallback timezone for a brand-new event whose timezone field hasn't been
#: chosen yet (matches the model default).
DEFAULT_TZ = zoneinfo.ZoneInfo("America/Los_Angeles")


def _classify_local_time(naive, tz):
    """Classify a naive local wall time in ``tz``.

    Returns ``"nonexistent"`` for a time inside a spring-forward gap, or
    ``"ambiguous"`` for a time inside a fall-back fold (where the same wall
    time occurs twice). Returns ``None`` for an ordinary, unambiguous time.

    The detection is stdlib-``zoneinfo`` only and avoids the ``datetime``
    equality fast path (two aware datetimes that share a ``tzinfo`` compare
    equal by wall time and ignore ``fold``), so it compares UTC offsets /
    round-trips the instant instead:

    * nonexistent — localizing then converting back through UTC lands on a
      *different* wall time (the gap has no valid instant);
    * ambiguous — the two ``fold`` values resolve to different UTC offsets
      (the wall time maps to two distinct instants).
    """
    a = naive.replace(tzinfo=tz, fold=0)
    b = naive.replace(tzinfo=tz, fold=1)
    roundtripped = a.astimezone(datetime.timezone.utc).astimezone(tz).replace(
        tzinfo=None
    )
    if roundtripped != naive:
        return "nonexistent"
    if a.utcoffset() != b.utcoffset():
        return "ambiguous"
    return None


class EventAdminForm(forms.ModelForm):
    """Enter/display ``open_at``/``close_at`` in the event's timezone.

    The split-datetime widget returns a **naive** local wall-clock time. In
    :meth:`clean` we localize it to the selected ``timezone`` (so it is stored
    as the correct UTC instant), and in :meth:`__init__` we show the stored UTC
    value converted back to local naive time (the widget renders naive values
    verbatim — ``to_current_timezone`` is a no-op on naive datetimes — so the
    admin sees local time, not UTC).
    """

    class Meta:
        model = Event
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        if instance is not None and instance.pk:
            tz = instance.timezone or DEFAULT_TZ
            if instance.open_at is not None:
                self.initial["open_at"] = instance.open_at.astimezone(tz).replace(
                    tzinfo=None
                )
            if instance.close_at is not None:
                self.initial["close_at"] = instance.close_at.astimezone(tz).replace(
                    tzinfo=None
                )

    def clean(self):
        cleaned_data = super().clean()
        tz = cleaned_data.get("timezone")
        if tz is None:
            # No timezone chosen: we cannot interpret the local wall-clock time.
            self.add_error(
                "timezone",
                "Select a timezone so the open/close times can be interpreted.",
            )
            return cleaned_data
        for name in ("open_at", "close_at"):
            value = cleaned_data.get(name)
            if value is None:
                continue
            # The datetime field parsed the wall-clock time the admin typed.
            # With USE_TZ=True the form returns it tagged as the current (UTC)
            # zone; we want it interpreted in the event's own timezone, so take
            # the naive wall-clock value and localize it to ``tz``.
            naive = value.replace(tzinfo=None) if timezone.is_aware(value) else value
            kind = _classify_local_time(naive, tz)
            if kind == "nonexistent":
                self.add_error(
                    name,
                    f"That local time does not exist in {tz} (it falls in the "
                    "spring-forward DST gap). Pick a different open/close time.",
                )
                continue
            if kind == "ambiguous":
                self.add_error(
                    name,
                    f"That local time is ambiguous in {tz} (it occurs twice "
                    "during the fall-back DST fold). Pick a different open/close "
                    "time.",
                )
                continue
            cleaned_data[name] = timezone.make_aware(naive, tz)

        open_at = cleaned_data.get("open_at")
        close_at = cleaned_data.get("close_at")
        if open_at and close_at and close_at <= open_at:
            raise forms.ValidationError("Close time must be later than open time.")
        return cleaned_data


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    form = EventAdminForm

    list_display = (
        "name",
        "date",
        "timezone",
        "status",
        "registration_count",
        "lottery_run_at",
    )
    list_filter = ("status", "timezone", "date")
    search_fields = ("name", "slug", "location")
    # Lifecycle/system fields are forward-only or counter-managed -> read-only.
    readonly_fields = (
        "status",
        "lottery_run_at",
        "next_staff_id",
        "created_at",
        "updated_at",
        "registration_count",
    )
    fieldsets = (
        (None, {"fields": ("slug", "name", "description")}),
        (
            "Schedule",
            {
                "fields": ("date", "location", "timezone", "open_at", "close_at"),
                "description": "open_at / close_at are entered and shown in the "
                "event's timezone (stored as UTC).",
            },
        ),
        ("Capacity caps", {"fields": ("x_seen", "y_waitlist", "z_applicants")}),
        (
            "Services offered",
            {
                "fields": (
                    "offers_flea_deworming",
                    "offers_microchip",
                    "offers_vaccination",
                    "offers_vet",
                )
            },
        ),
        (
            "Lifecycle (read-only)",
            {"fields": ("status", "lottery_run_at", "next_staff_id")},
        ),
        ("Metadata", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Registrations")
    def registration_count(self, obj):
        return obj.registrations.count()
