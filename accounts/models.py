"""User model for CWAC staff (admin + volunteer)."""
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.db import models


class UserManager(DjangoUserManager):
    """Manager that keeps ``role`` consistent with the Django privilege flags.

    CWAC has exactly two staff profiles (Decision 16 / FR-30):

    * **Admin** = a Django *superuser* — ``is_staff=True``, ``is_superuser=True``,
      ``role=admin`` (full Django-admin access + every capability).
    * **Volunteer** — ``is_staff=False``, ``is_superuser=False``, ``role=volunteer``
      (custom clinic views only; cannot enter the Django admin).

    ``create_user``/``acreate_user`` and ``create_superuser``/``acreate_superuser``
    each **reject** any argument combination that would break that invariant, so there
    is no path through this manager that provisions a volunteer-role superuser or a
    privileged volunteer. Subclasses the contrib ``UserManager`` so the async entry
    points (``acreate_user``/``acreate_superuser``) and ``make_random_password`` are
    preserved; all four create-methods are overridden so the invariant holds on both
    the sync and async paths (the async methods call ``_acreate_user`` directly, not
    the sync overrides).
    """

    use_in_migrations = True

    @staticmethod
    def _reject_privileged_volunteer(is_staff, is_superuser, role):
        if is_staff or is_superuser:
            raise ValueError(
                "create_user/acreate_user provision a Volunteer "
                "(is_staff=False, is_superuser=False). "
                "Use create_superuser()/acreate_superuser() to create an Admin."
            )
        if role is not None and role != User.Role.VOLUNTEER:
            raise ValueError(
                "create_user/acreate_user provision a Volunteer (role=volunteer); "
                "an Admin (role=admin) must be created via create_superuser()."
            )

    @staticmethod
    def _reject_underpowered_admin(is_staff, is_superuser, role):
        if is_staff is not None and is_staff is not True:
            raise ValueError("An Admin must have is_staff=True.")
        if is_superuser is not None and is_superuser is not True:
            raise ValueError("An Admin must have is_superuser=True.")
        if role is not None and role != User.Role.ADMIN:
            raise ValueError("An Admin must have role=admin.")

    def create_user(self, username, email=None, password=None, **extra_fields):
        self._reject_privileged_volunteer(
            extra_fields.get("is_staff", False),
            extra_fields.get("is_superuser", False),
            extra_fields.get("role"),
        )
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", User.Role.VOLUNTEER)
        return super().create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        self._reject_underpowered_admin(
            extra_fields.get("is_staff"),
            extra_fields.get("is_superuser"),
            extra_fields.get("role"),
        )
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)

    async def acreate_user(self, username, email=None, password=None, **extra_fields):
        self._reject_privileged_volunteer(
            extra_fields.get("is_staff", False),
            extra_fields.get("is_superuser", False),
            extra_fields.get("role"),
        )
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", User.Role.VOLUNTEER)
        return await super().acreate_user(username, email, password, **extra_fields)

    async def acreate_superuser(
        self, username, email=None, password=None, **extra_fields
    ):
        self._reject_underpowered_admin(
            extra_fields.get("is_staff"),
            extra_fields.get("is_superuser"),
            extra_fields.get("role"),
        )
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        return await super().acreate_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """Staff account.

    Privileges are differentiated (Decision 16 / FR-30): **Admin-only** =
    create/configure/delete events, run the lottery, and export; **both roles**
    perform all clinic operations (lookup, edit, add, remove, check-in, print,
    manual entry, assign AnimalID). An Admin is a Django **superuser**
    (``is_staff=True`` + ``is_superuser=True`` + ``role=admin`` — full Django-admin
    access, provisioned via ``createsuperuser``/``ensure_admin``); a Volunteer is
    ``is_staff=False``/``is_superuser=False``/``role=volunteer`` and reaches only the
    custom clinic views (admin-only views gate on ``role == admin``). ``UserManager``
    and ``clean()`` together keep those three flags consistent, so an inconsistent
    combination (e.g. a volunteer-role superuser) can be neither created nor saved.
    This custom user model is referenced by ``AUTH_USER_MODEL`` in
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

    objects = UserManager()

    def clean(self):
        super().clean()
        # An Admin is all three privileged flags together; a Volunteer is none.
        # Any partial combination (e.g. is_staff=True but role=volunteer, or
        # role=admin but is_superuser=False) is rejected.
        if self.is_staff or self.is_superuser or self.role == self.Role.ADMIN:
            if not (
                self.is_staff and self.is_superuser and self.role == self.Role.ADMIN
            ):
                raise ValidationError(
                    "Privilege flags are inconsistent: an Admin is "
                    "is_staff=True + is_superuser=True + role=admin; "
                    "a Volunteer is is_staff=False + is_superuser=False + "
                    "role=volunteer."
                )

    def __str__(self):
        return self.username
