from decimal import Decimal

from rest_framework.test import APIClient

from routing.exceptions import (
    LocationNotFoundError,
    NoFeasibleFuelPlanError,
    RoutingProviderError,
)


FUEL_PLAN_URL = "/api/routes/fuel-plan/"


def coordinate_request():
    return {
        "start": {"lat": 30.2672, "lng": -97.7431},
        "destination": {"lat": 39.7392, "lng": -104.9903},
    }


def test_fuel_plan_endpoint_returns_success(monkeypatch):
    def fake_build_route_fuel_plan(**kwargs):
        assert kwargs["start"] == {
            "lat": Decimal("30.267200"),
            "lng": Decimal("-97.743100"),
        }
        return {
            "route": {"distance_miles": Decimal("100.50"), "geometry": []},
            "fuel_plan": {
                "total_cost": Decimal("30.00"),
                "stops": [
                    {
                        "station_id": 1,
                        "price_per_gallon": Decimal("3.25"),
                        "cost": Decimal("30.00"),
                    }
                ],
            },
        }

    monkeypatch.setattr(
        "routing.views.build_route_fuel_plan", fake_build_route_fuel_plan
    )

    response = APIClient().post(FUEL_PLAN_URL, coordinate_request(), format="json")

    assert response.status_code == 200
    assert response.json() == {
        "route": {"distance_miles": 100.5, "geometry": []},
        "fuel_plan": {
            "total_cost": 30.0,
            "stops": [
                {
                    "station_id": 1,
                    "price_per_gallon": 3.25,
                    "cost": 30.0,
                }
            ],
        },
    }


def test_fuel_plan_endpoint_maps_no_feasible_plan(monkeypatch):
    def fake_build_route_fuel_plan(**kwargs):
        raise NoFeasibleFuelPlanError("internal graph exhausted at station_id=4812")

    monkeypatch.setattr(
        "routing.views.build_route_fuel_plan", fake_build_route_fuel_plan
    )

    response = APIClient().post(FUEL_PLAN_URL, coordinate_request(), format="json")

    assert response.status_code == 422
    assert response.json()["error"] == "no_feasible_fuel_plan"
    assert (
        response.json()["message"]
        == "A route was found, but the available fuel-price dataset does not contain "
        "enough reachable fuel stations to complete the trip within a 500-mile "
        "vehicle range."
    )


def test_fuel_plan_endpoint_maps_location_not_found(monkeypatch):
    def fake_build_route_fuel_plan(**kwargs):
        raise LocationNotFoundError("geocoder returned ZERO_RESULTS for raw query")

    monkeypatch.setattr(
        "routing.views.build_route_fuel_plan", fake_build_route_fuel_plan
    )

    response = APIClient().post(FUEL_PLAN_URL, coordinate_request(), format="json")

    assert response.status_code == 422
    assert response.json()["error"] == "location_not_found"
    assert (
        response.json()["message"]
        == "Start or destination could not be resolved to a USA location."
    )


def test_fuel_plan_endpoint_maps_routing_provider_error(monkeypatch):
    def fake_build_route_fuel_plan(**kwargs):
        raise RoutingProviderError("ORS 500: token quota abc123 exhausted")

    monkeypatch.setattr(
        "routing.views.build_route_fuel_plan", fake_build_route_fuel_plan
    )

    response = APIClient().post(FUEL_PLAN_URL, coordinate_request(), format="json")

    assert response.status_code == 503
    assert response.json()["error"] == "routing_unavailable"
    assert response.json()["message"] == "Route calculation is temporarily unavailable."


def test_fuel_plan_endpoint_rejects_invalid_request(monkeypatch):
    def fail_if_called(**kwargs):
        raise AssertionError("planner should not be called for invalid requests")

    monkeypatch.setattr("routing.views.build_route_fuel_plan", fail_if_called)

    response = APIClient().post(
        FUEL_PLAN_URL,
        {"start": "Austin, TX", "corridor_miles": 99},
        format="json",
    )

    assert response.status_code == 400
    assert "destination" in response.json()


def test_django_settings_load(settings):
    assert "rest_framework" in settings.INSTALLED_APPS
    assert "fuel" in settings.INSTALLED_APPS
    assert "routing" in settings.INSTALLED_APPS


def test_drf_is_json_only(settings):
    assert settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] == [
        "rest_framework.renderers.JSONRenderer",
    ]
    assert settings.REST_FRAMEWORK["DEFAULT_PARSER_CLASSES"] == [
        "rest_framework.parsers.JSONParser",
    ]


def test_database_uses_sqlite(settings):
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert settings.DATABASES["default"]["NAME"] == settings.BASE_DIR / "db.sqlite3"


def test_routes_are_mounted_under_api_routes(settings):
    from spotter_backend.urls import urlpatterns

    api_route = next(
        pattern for pattern in urlpatterns if str(pattern.pattern) == "api/routes/"
    )

    assert api_route.urlconf_name.__name__ == "routing.urls"


def test_allowed_hosts_are_local_only():
    from spotter_backend import settings as project_settings

    assert project_settings.ALLOWED_HOSTS == ["localhost", "127.0.0.1"]


def test_required_route_planner_settings(settings):
    assert settings.OSRM_BASE_URL == "https://router.project-osrm.org"
    assert (
        settings.CENSUS_GEOCODER_BASE_URL
        == "https://geocoding.geo.census.gov/geocoder"
    )
    assert settings.DEFAULT_ROUTE_CORRIDOR_MILES == 10
    assert settings.MAX_ROUTE_CORRIDOR_MILES == 25
    assert settings.DEFAULT_MAX_RANGE_MILES == 500
    assert settings.DEFAULT_MILES_PER_GALLON == 10
