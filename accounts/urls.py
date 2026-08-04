"""Session-authentication routes for CWAC staff."""

from django.urls import path

from .views import StaffLoginView, StaffLogoutView

app_name = "accounts"

urlpatterns = [
    path("login/", StaffLoginView.as_view(), name="login"),
    path("logout/", StaffLogoutView.as_view(), name="logout"),
]
