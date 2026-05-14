from django.urls import path

from routing.views import FuelPlanView


urlpatterns = [
    path("fuel-plan/", FuelPlanView.as_view(), name="fuel-plan"),
]
