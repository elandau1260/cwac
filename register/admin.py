"""Django admin for registrations and animals (back-office).

The allocation-managed fields (``animal_id``, ``id_source``) and the
fire-and-forget SMS/token state are read-only here — IDs are assigned only by
the allocation services, never typed by hand. Animals are edited inline.
"""
from django.contrib import admin

from .models import Animal, Registration


class AnimalInline(admin.TabularInline):
    model = Animal
    extra = 0
    fields = (
        "name",
        "species",
        "age",
        "sex",
        "breed",
        "color",
        "services_requested",
        "last_vaccinated_date",
        "medical_concern",
    )


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "animal_id",
        "last_name",
        "first_name",
        "event",
        "status",
        "language",
        "creation_source",
        "printed_at",
        "checked_in_at",
    )
    list_filter = (
        "status",
        "language",
        "creation_source",
        "id_source",
        "event",
    )
    search_fields = ("first_name", "last_name", "phone", "email", "animal_id", "edit_token")
    # Allocation-managed and system-managed fields -> display only.
    readonly_fields = (
        "animal_id",
        "id_source",
        "edit_token",
        "result_sms_state",
        "result_sms_sent_at",
        "admitted_by_user",
        "admitted_at",
        "printed_at",
        "checked_in_at",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("event", "created_by_user")

    fieldsets = (
        (None, {"fields": ("event", "status", "language")}),
        ("Owner", {"fields": ("first_name", "last_name", "phone", "email", "address")}),
        ("Animal ID", {"fields": ("animal_id", "id_source")}),
        ("SMS", {"fields": ("sms_opt_out", "result_sms_state", "result_sms_sent_at")}),
        (
            "Provenance",
            {
                "fields": (
                    "creation_source",
                    "created_by_user",
                    "admitted_by_user",
                    "admitted_at",
                )
            },
        ),
        ("Clinic day", {"fields": ("printed_at", "checked_in_at")}),
        ("Token / metadata", {"fields": ("edit_token", "created_at", "updated_at")}),
    )
    inlines = [AnimalInline]
