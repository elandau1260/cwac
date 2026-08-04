"""Admin-only event-management helper routes."""

from django.urls import path

from .views import EventFlyerView, EventQrDownloadView

app_name = "events"

urlpatterns = [
    path("<int:pk>/flyer/", EventFlyerView.as_view(), name="flyer"),
    path("<int:pk>/flyer/qr.jpg", EventQrDownloadView.as_view(), name="qr_download"),
]
