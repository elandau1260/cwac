"""User model for CWAC staff (admin + volunteer)."""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Staff account.

    Both roles share the same privileges in V1 (Decision 7); ``role`` is for
    logging/auditing only. This custom user model is referenced by
    ``AUTH_USER_MODEL`` in ``config/settings/base.py`` and must exist before
    the first migration.
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
