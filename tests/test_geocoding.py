from decimal import Decimal

import pytest

from fuel.models import LocationCache
from routing.exceptions import LocationNotFoundError
from routing.services.geocoding import GeocodedLocation, normalize_query, resolve_location


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
    def geocode_one(self, query):
        return None


def test_normalize_query_collapses_case_and_spacing():
    assert normalize_query("  Austin,   TX ") == "austin, tx"


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
    cached = LocationCache.objects.get(query="austin, tx")
    assert cached.longitude == Decimal("-97.743100")
    assert cached.raw_response == {"ok": True}


@pytest.mark.django_db
def test_resolve_location_raises_when_provider_has_no_match():
    with pytest.raises(LocationNotFoundError):
        resolve_location("Nope", provider=MissingGeocoder())
