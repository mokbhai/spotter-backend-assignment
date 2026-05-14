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
