"""Tests for the CWAC user/manager privilege invariant (F1, round-7 audit).

Covers: sync + async manager paths; rejection of every inconsistent argument
combination; the ``createsuperuser`` command; model + admin-form validation;
and the 0002 data migration that repairs a pre-existing volunteer-role
superuser. (TC-059.)
"""
import asyncio
import importlib
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

from accounts.models import UserManager, User

UserModel = get_user_model()


class UserManagerSyncTest(TestCase):
    """create_user/create_superuser enforce the Admin/Volunteer invariant."""

    def test_create_user_provisions_a_volunteer(self):
        u = UserModel.objects.create_user("vole", "v@x.com", "sup3rs3cret!")
        self.assertEqual(u.role, User.Role.VOLUNTEER)
        self.assertFalse(u.is_staff)
        self.assertFalse(u.is_superuser)

    def test_create_superuser_provisions_an_admin(self):
        u = UserModel.objects.create_superuser("boss", "b@x.com", "sup3rs3cret!")
        self.assertEqual(u.role, User.Role.ADMIN)
        self.assertTrue(u.is_staff)
        self.assertTrue(u.is_superuser)

    # --- create_user must reject every privileged combination ----------------
    def test_create_user_rejects_is_staff(self):
        with self.assertRaises(ValueError):
            UserModel.objects.create_user("x", "x@x.com", "pw", is_staff=True)

    def test_create_user_rejects_is_superuser(self):
        with self.assertRaises(ValueError):
            UserModel.objects.create_user("x", "x@x.com", "pw", is_superuser=True)

    def test_create_user_rejects_role_admin(self):
        with self.assertRaises(ValueError):
            UserModel.objects.create_user("x", "x@x.com", "pw", role=User.Role.ADMIN)

    # --- create_superuser must reject every underpowered combination ---------
    def test_create_superuser_rejects_is_staff_false(self):
        with self.assertRaises(ValueError):
            UserModel.objects.create_superuser("x", "x@x.com", "pw", is_staff=False)

    def test_create_superuser_rejects_is_superuser_false(self):
        with self.assertRaises(ValueError):
            UserModel.objects.create_superuser("x", "x@x.com", "pw", is_superuser=False)

    def test_create_superuser_rejects_role_volunteer(self):
        with self.assertRaises(ValueError):
            UserModel.objects.create_superuser(
                "x", "x@x.com", "pw", role=User.Role.VOLUNTEER
            )

    def test_manager_preserves_async_entry_points(self):
        # Subclasses the contrib UserManager, so the async entry points exist;
        # both are our overrides (they enforce the invariant on the async path).
        from django.contrib.auth.models import UserManager as ContribUserManager

        self.assertIsInstance(UserModel.objects, UserManager)
        self.assertIsInstance(UserModel.objects, ContribUserManager)
        self.assertTrue(callable(getattr(UserModel.objects, "acreate_user", None)))
        self.assertTrue(callable(getattr(UserModel.objects, "acreate_superuser", None)))
        self.assertIsNot(UserManager.acreate_user, ContribUserManager.acreate_user)
        self.assertIsNot(UserManager.acreate_superuser, ContribUserManager.acreate_superuser)


class UserManagerAsyncTest(TransactionTestCase):
    """The async entry points go through _acreate_user, not the sync overrides,
    so they are overridden directly — verify they enforce the same invariant."""

    def test_acreate_user_provisions_a_volunteer(self):
        u = asyncio.run(
            UserModel.objects.acreate_user("vole", "v@x.com", "sup3rs3cret!")
        )
        self.assertEqual(u.role, User.Role.VOLUNTEER)
        self.assertFalse(u.is_staff)
        self.assertFalse(u.is_superuser)

    def test_acreate_superuser_provisions_an_admin(self):
        u = asyncio.run(
            UserModel.objects.acreate_superuser("boss", "b@x.com", "sup3rs3cret!")
        )
        self.assertEqual(u.role, User.Role.ADMIN)
        self.assertTrue(u.is_staff)
        self.assertTrue(u.is_superuser)

    def test_acreate_user_rejects_role_admin(self):
        with self.assertRaises(ValueError):
            asyncio.run(
                UserModel.objects.acreate_user(
                    "x", "x@x.com", "pw", role=User.Role.ADMIN
                )
            )

    def test_acreate_superuser_rejects_role_volunteer(self):
        with self.assertRaises(ValueError):
            asyncio.run(
                UserModel.objects.acreate_superuser(
                    "x", "x@x.com", "pw", role=User.Role.VOLUNTEER
                )
            )


class CreateSuperuserCommandTest(TestCase):
    """The real ``createsuperuser`` management command yields a full Admin."""

    def test_createsuperuser_makes_admin(self):
        with patch.dict(os.environ, {"DJANGO_SUPERUSER_PASSWORD": "sup3rs3cret!"}):
            call_command(
                "createsuperuser",
                "--noinput",
                "--username",
                "boot",
                "--email",
                "boot@x.com",
                stdout=open(os.devnull, "w"),
            )
        u = UserModel.objects.get(username="boot")
        self.assertEqual(u.role, User.Role.ADMIN)
        self.assertTrue(u.is_staff)
        self.assertTrue(u.is_superuser)
        self.assertTrue(u.check_password("sup3rs3cret!"))


class UserModelValidationTest(TestCase):
    """User.clean() rejects any partial privilege combination."""

    def _user(self, **overrides):
        u = UserModel(username="u", email="u@x.com")
        for k, v in overrides.items():
            setattr(u, k, v)
        return u

    def test_clean_accepts_full_admin(self):
        self._user(is_staff=True, is_superuser=True, role=User.Role.ADMIN).clean()

    def test_clean_accepts_plain_volunteer(self):
        self._user().clean()  # defaults: no flags, role=volunteer

    def test_clean_rejects_staff_without_admin_role(self):
        u = self._user(is_staff=True)  # role still volunteer
        with self.assertRaises(ValidationError):
            u.clean()

    def test_clean_rejects_admin_role_without_superuser(self):
        u = self._user(role=User.Role.ADMIN)  # flags still False
        with self.assertRaises(ValidationError):
            u.clean()

    def test_clean_rejects_superuser_without_staff(self):
        u = self._user(is_superuser=True)  # is_staff False, role volunteer
        with self.assertRaises(ValidationError):
            u.clean()

    def test_full_clean_blocks_inconsistent_user(self):
        u = self._user(is_staff=True)  # inconsistent
        with self.assertRaises(ValidationError):
            u.full_clean()


class UserAdminFormValidationTest(TestCase):
    """The Django admin change form runs model.clean() via full_clean(), so an
    editor cannot save an inconsistent combination through the admin."""

    def test_change_form_rejects_inconsistent_flags(self):
        from django.contrib.auth.forms import UserChangeForm

        volunteer = UserModel.objects.create_user("vole", "v@x.com", "sup3rs3cret!")
        form = UserChangeForm(
            instance=volunteer,
            data={
                "username": "vole",
                "email": "v@x.com",
                "role": User.Role.ADMIN,  # admin role ...
                "is_active": "on",
                # ... but is_staff/is_superuser left False -> inconsistent
            },
        )
        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors)


class RepairMigrationTest(TestCase):
    """0002 repairs a pre-existing volunteer-role superuser into a full Admin
    (the state produced by ``createsuperuser`` before the custom manager)."""

    def _repair_module(self):
        return importlib.import_module("accounts.migrations.0002_manager_and_repair")

    def test_repair_flips_volunteer_role_superuser_to_admin(self):
        from django.apps import apps

        mod = self._repair_module()
        admin = UserModel.objects.create_superuser("legacy", "l@x.com", "sup3rs3cret!")
        # Simulate pre-manager legacy data: a superuser stuck at the model default role.
        UserModel.objects.filter(pk=admin.pk).update(role=User.Role.VOLUNTEER)
        admin.refresh_from_db()
        self.assertEqual(admin.role, User.Role.VOLUNTEER)  # precondition

        mod.repair_superuser_roles(apps, schema_editor=None)

        admin.refresh_from_db()
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_staff)

    def test_repair_does_not_touch_volunteers(self):
        from django.apps import apps

        mod = self._repair_module()
        volunteer = UserModel.objects.create_user("vole", "v@x.com", "sup3rs3cret!")
        mod.repair_superuser_roles(apps, schema_editor=None)
        volunteer.refresh_from_db()
        self.assertEqual(volunteer.role, User.Role.VOLUNTEER)
        self.assertFalse(volunteer.is_superuser)
