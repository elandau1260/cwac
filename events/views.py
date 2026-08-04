"""Admin-only event flyer and QR-code views (Phase 2)."""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import DetailView

from accounts.views import AdminRequiredMixin

from .models import Event
from .services_qr import qr_jpeg


def signup_url(request, event):
    """Return this event's absolute public signup URL.

    The public view itself arrives in Phase 3, but its locked route is already
    ``/r/<slug>/``. ``build_absolute_uri`` keeps local/staging/production flyer
    links tied to the host from which the Admin requested them.
    """
    return request.build_absolute_uri(f"/r/{event.slug}/")


class EventFlyerView(AdminRequiredMixin, DetailView):
    """Show the event details, copyable signup URL, and flyer QR image."""

    model = Event
    template_name = "events/flyer.html"
    context_object_name = "event"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["signup_url"] = signup_url(self.request, self.object)
        return context


class EventQrDownloadView(AdminRequiredMixin, View):
    """Download a JPG QR code whose payload is the public signup URL."""

    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        response = HttpResponse(
            qr_jpeg(signup_url(request, event)),
            content_type="image/jpeg",
        )
        disposition = "attachment" if request.GET.get("download") == "1" else "inline"
        response["Content-Disposition"] = (
            f'{disposition}; filename="{event.slug}-signup-qr.jpg"'
        )
        return response
