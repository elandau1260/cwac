from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Django-admin registration for the custom ``User``.

    Surfaces ``role`` alongside the privilege flags. The privilege invariant
    (an Admin is ``is_staff`` + ``is_superuser`` + ``role=admin``; a Volunteer is
    none of those) is enforced by ``User.clean()``, which every ModelForm —
    including the admin's add/change forms — runs via ``full_clean()``. So an
    editor cannot save a volunteer-role superuser or a privileged volunteer
    through the admin any more than through the manager.

    Admins are normally provisioned with ``createsuperuser`` / ``ensure_admin``
    (which set all three flags); this form is used to manage Volunteer accounts
    and to adjust either role.
    """

    model = User
    list_display = ("username", "email", "role", "is_staff", "is_superuser", "is_active")
    list_filter = ("role", "is_staff", "is_superuser", "is_active", "groups")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        (
            "Role & permissions",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2", "role"),
            },
        ),
    )
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
