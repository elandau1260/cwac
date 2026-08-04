"""Authentication views and access-control helpers for CWAC staff."""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy

from .models import User


class StaffLoginView(LoginView):
    """Username/password login shared by Admins and Volunteers (FR-30)."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True


class StaffLogoutView(LogoutView):
    """End the staff session and return to the login page."""

    next_page = reverse_lazy("accounts:login")


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Require the authenticated user to have CWAC's Admin role.

    Anonymous users are redirected to the staff login by
    :class:`LoginRequiredMixin`; an authenticated Volunteer receives HTTP 403
    rather than being sent through a misleading login loop. Custom Admin-only
    views (event flyer/QR now, lottery and export later) share this gate.
    """

    def test_func(self):
        return self.request.user.role == User.Role.ADMIN
