"""User model for CWAC staff (admin + volunteer)."""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Staff account.

    Privileges are differentiated (Decision 16 / FR-30): **Admin-only** =
    create/configure/delete events, run the lottery, and export; **both roles**
    perform all clinic operations (lookup, edit, add, remove, check-in, print,
    manual entry, assign AnimalID). Provisioning keeps ``is_staff`` consistent
    with ``role`` (Admin -> ``True`` for Django-admin access; Volunteer ->
    ``False``); Admin-only custom views are gated by ``role == admin``. This
    custom user model is referenced by ``AUTH_USER_MODEL`` in
    ``config/settings/base.py`` and must exist before the first migration.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        VOLUNTEER = "volunteer", "Volunteer"

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.VOLUNTEER,
    )

    def __str__(self):
        return self.username
