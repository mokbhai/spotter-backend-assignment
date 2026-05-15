from django.contrib import admin
from django.urls import include, path

from routing.views import OpenPanelConfigView


urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/openpanel/config/",
        OpenPanelConfigView.as_view(),
        name="openpanel-config",
    ),
    path("api/routes/", include("routing.urls")),
]
