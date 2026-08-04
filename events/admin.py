"""Django admin for events (back-office).

The notable piece is :class:`EventAdminForm`: ``open_at``/``close_at`` are stored
as UTC (``USE_TZ=True``) but the admin enters and reads them in the **event's
own timezone**, so the admin always works in local wall-clock time for that
clinic. A naive local input from the split-datetime widget is localized to the
selected timezone on save; on load the stored UTC value is shown in local time.
"""
import zoneinfo

from django import forms
from django.contrib import admin
from django.utils import timezone

from .models import Event

#: Fallback timezone for a brand-new event whose timezone field hasn't been
#: chosen yet (matches the model default).
DEFAULT_TZ = zoneinfo.ZoneInfo("America/Los_Angeles")


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
