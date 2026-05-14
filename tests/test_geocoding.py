from decimal import Decimal

import pytest
import requests

from fuel.models import LocationCache
from routing.exceptions import LocationNotFoundError, RoutingProviderError
from routing.services.geocoding import (
    CensusGeocoder,
    GeocodedLocation,
    normalize_query,
    resolve_location,
)


class FakeGeocoder:
    def __init__(self):
        self.calls = []

    def geocode_one(self, query):
        self.calls.append(query)
        return GeocodedLocation(
            query=query,
            latitude=Decimal("30.267200"),
            longitude=Decimal("-97.743100"),
            provider="fake",
            raw_response={"ok": True},
        )


class MissingGeocoder:
    def __init__(self):
        self.calls = []

    def geocode_one(self, query):
        self.calls.append(query)
        return None


class FakeResponse:
    def __init__(self, payload=None, json_error=None):
        self.payload = payload
        self.json_error = json_error

    def raise_for_status(self):
        return None

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def test_normalize_query_collapses_case_and_spacing():
    assert normalize_query("  Austin,   TX ") == "austin, tx"


def test_census_geocoder_success_parses_coordinates(monkeypatch, settings):
    settings.CENSUS_GEOCODER_BASE_URL = "https://example.test/geocoder"
    payload = {
        "result": {
            "addressMatches": [
                {
                    "coordinates": {"x": -97.7431, "y": 30.2672},
                    "matchedAddress": "Austin, TX",
                }
            ]
        }
    }
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse(payload)

    monkeypatch.setattr("routing.services.geocoding.requests.get", fake_get)

    location = CensusGeocoder(timeout=3).geocode_one("Austin, TX")

    assert location == GeocodedLocation(
        query="Austin, TX",
        latitude=Decimal("30.2672"),
        longitude=Decimal("-97.7431"),
        provider="census",
        raw_response=payload["result"]["addressMatches"][0],
    )
    assert calls == [
        (
            "https://example.test/geocoder/locations/onelineaddress",
            {
                "address": "Austin, TX",
                "benchmark": "Public_AR_Current",
                "format": "json",
            },
            3,
        )
    ]


def test_census_geocoder_returns_none_when_provider_has_no_matches(monkeypatch):
    monkeypatch.setattr(
        "routing.services.geocoding.requests.get",
        lambda *args, **kwargs: FakeResponse({"result": {"addressMatches": []}}),
    )

    assert CensusGeocoder().geocode_one("Nope") is None


def test_census_geocoder_maps_http_failure_to_provider_error(monkeypatch):
    def fail_get(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setattr("routing.services.geocoding.requests.get", fail_get)

    with pytest.raises(RoutingProviderError):
        CensusGeocoder().geocode_one("Austin, TX")


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(json_error=ValueError("bad json")),
        FakeResponse({"result": {"addressMatches": [{"coordinates": {"x": -97.7431}}]}}),
        FakeResponse({"result": {"addressMatches": [{"coordinates": {"x": "bad", "y": 30.2672}}]}}),
    ],
)
def test_census_geocoder_maps_malformed_response_to_provider_error(monkeypatch, response):
    monkeypatch.setattr(
        "routing.services.geocoding.requests.get",
        lambda *args, **kwargs: response,
    )

    with pytest.raises(RoutingProviderError):
        CensusGeocoder().geocode_one("Austin, TX")


@pytest.mark.django_db
def test_resolve_location_uses_cache_before_provider():
    LocationCache.objects.create(
        query="austin, tx",
        latitude=Decimal("30.267200"),
        longitude=Decimal("-97.743100"),
        provider="cached",
    )
    provider = FakeGeocoder()

    location = resolve_location("Austin, TX", provider=provider)

    assert location.provider == "cached"
    assert location.latitude == Decimal("30.267200")
    assert provider.calls == []


@pytest.mark.django_db
def test_resolve_location_stores_provider_result_with_normalized_query():
    location = resolve_location("Austin, TX", provider=FakeGeocoder())

    assert location.provider == "fake"
    assert location.query == "austin, tx"
    cached = LocationCache.objects.get(query="austin, tx")
    assert cached.longitude == Decimal("-97.743100")
    assert cached.raw_response == {"ok": True}


@pytest.mark.django_db
def test_resolve_location_raises_when_provider_has_no_match():
    with pytest.raises(LocationNotFoundError):
        resolve_location("Nope", provider=MissingGeocoder())


@pytest.mark.django_db
def test_resolve_location_rejects_blank_query_without_provider_call():
    provider = MissingGeocoder()

    with pytest.raises(LocationNotFoundError):
        resolve_location("   ", provider=provider)

    assert provider.calls == []
