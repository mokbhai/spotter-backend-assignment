from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from routing.views import OpenPanelConfigView


urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/openpanel/config/",
        OpenPanelConfigView.as_view(),
        name="openpanel-config",
    ),
    path("api/routes/", include("routing.urls")),
    re_path(
        r"^(?!api(?:/|$)|admin(?:/|$)).*$",
        RedirectView.as_view(
            url="/static/routing/architecture-api-demo.html",
            permanent=False,
        ),
        name="frontend-demo-fallback",
    ),
]
