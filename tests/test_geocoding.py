from decimal import Decimal

import pytest
import requests

from fuel.models import LocationCache
from routing.exceptions import LocationNotFoundError, RoutingProviderError
from routing.services.geocoding import (
    CensusGeocoder,
    CensusBatchStationGeocoder,
    GeocodedLocation,
    StationGeocodeResult,
    apply_station_geocoding_results,
    build_census_batch_input,
    normalize_query,
    parse_census_batch_response,
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
def test_build_census_batch_input_includes_station_id_and_address_parts():
    from fuel.models import FuelStation

    station = FuelStation.objects.create(
        opis_truckstop_id="123",
        name="Austin Fuel",
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.249"),
        source_row_hash="station-batch-input",
    )

    csv_content = build_census_batch_input([station])

    assert csv_content == f'{station.id},I-35,Austin,TX,\r\n'


def test_parse_census_batch_response_extracts_coordinates():
    results = parse_census_batch_response(
        '"123","I-35, Austin, TX","Match","Exact","I-35, Austin, TX","-97.743100,30.267200","123456789012345","L"\n'
    )

    assert results == [
        StationGeocodeResult(
            station_id="123",
            matched=True,
            latitude=Decimal("30.267200"),
            longitude=Decimal("-97.743100"),
            score=None,
        )
    ]


def test_parse_census_batch_response_marks_no_match():
    results = parse_census_batch_response('"124","Missing","No_Match","","","","",""\n')

    assert results == [
        StationGeocodeResult(
            station_id="124",
            matched=False,
            latitude=None,
            longitude=None,
            score=None,
        )
    ]


def test_parse_census_batch_response_rejects_malformed_match_coordinates():
    with pytest.raises(RoutingProviderError, match="Census batch geocoder returned malformed"):
        parse_census_batch_response(
            '"123","I-35, Austin, TX","Match","Exact","I-35, Austin, TX","bad","1","L"\n'
        )


@pytest.mark.django_db
def test_apply_station_geocoding_results_marks_matched_and_unmatched():
    from fuel.models import FuelStation

    matched = FuelStation.objects.create(
        opis_truckstop_id="123",
        name="Austin Fuel",
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.249"),
        source_row_hash="matched-station",
    )
    unmatched = FuelStation.objects.create(
        opis_truckstop_id="124",
        name="Missing Fuel",
        address="Missing",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.249"),
        source_row_hash="unmatched-station",
        latitude=Decimal("30.000000"),
        longitude=Decimal("-97.000000"),
        geocoding_score=Decimal("0.500"),
        is_active=True,
    )

    summary = apply_station_geocoding_results(
        [
            StationGeocodeResult(
                station_id=str(matched.id),
                matched=True,
                latitude=Decimal("30.267200"),
                longitude=Decimal("-97.743100"),
                score=None,
            ),
            StationGeocodeResult(
                station_id=str(unmatched.id),
                matched=False,
                latitude=None,
                longitude=None,
            ),
        ]
    )

    matched.refresh_from_db()
    unmatched.refresh_from_db()
    assert summary.matched == 1
    assert summary.unmatched == 1
    assert summary.failed == 0
    assert matched.latitude == Decimal("30.267200")
    assert matched.longitude == Decimal("-97.743100")
    assert matched.geocoding_score is None
    assert matched.geocoding_status == FuelStation.GeocodingStatus.MATCHED
    assert matched.is_active is True
    assert unmatched.latitude is None
    assert unmatched.longitude is None
    assert unmatched.geocoding_score is None
    assert unmatched.geocoding_status == FuelStation.GeocodingStatus.UNMATCHED
    assert unmatched.is_active is False


@pytest.mark.django_db
def test_apply_station_geocoding_results_counts_missing_station_as_failed():
    summary = apply_station_geocoding_results(
        [
            StationGeocodeResult(
                station_id="999999",
                matched=True,
                latitude=Decimal("30.267200"),
                longitude=Decimal("-97.743100"),
            )
        ]
    )

    assert summary.matched == 0
    assert summary.unmatched == 0
    assert summary.failed == 1


@pytest.mark.django_db
def test_apply_station_geocoding_results_rejects_matched_result_without_coordinates():
    from fuel.models import FuelStation

    station = FuelStation.objects.create(
        opis_truckstop_id="123",
        name="Austin Fuel",
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.249"),
        source_row_hash="missing-coordinates-station",
    )

    summary = apply_station_geocoding_results(
        [
            StationGeocodeResult(
                station_id=str(station.id),
                matched=True,
                latitude=None,
                longitude=Decimal("-97.743100"),
            )
        ]
    )

    station.refresh_from_db()
    assert summary.matched == 0
    assert summary.unmatched == 0
    assert summary.failed == 1
    assert station.latitude is None
    assert station.longitude is None
    assert station.geocoding_status == FuelStation.GeocodingStatus.PENDING
    assert station.is_active is False


@pytest.mark.django_db
def test_apply_station_geocoding_results_rejects_out_of_range_coordinates():
    from fuel.models import FuelStation

    station = FuelStation.objects.create(
        opis_truckstop_id="123",
        name="Austin Fuel",
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.249"),
        source_row_hash="out-of-range-station",
    )

    summary = apply_station_geocoding_results(
        [
            StationGeocodeResult(
                station_id=str(station.id),
                matched=True,
                latitude=Decimal("91.000000"),
                longitude=Decimal("-97.743100"),
            )
        ]
    )

    station.refresh_from_db()
    assert summary.matched == 0
    assert summary.unmatched == 0
    assert summary.failed == 1
    assert station.latitude is None
    assert station.longitude is None
    assert station.geocoding_status == FuelStation.GeocodingStatus.PENDING
    assert station.is_active is False


@pytest.mark.django_db
def test_census_batch_station_geocoder_posts_and_parses(monkeypatch, settings):
    from fuel.models import FuelStation

    settings.CENSUS_GEOCODER_BASE_URL = "https://example.test/geocoder"
    station = FuelStation.objects.create(
        opis_truckstop_id="123",
        name="Austin Fuel",
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.249"),
        source_row_hash="batch-post-station",
    )
    calls = []

    class FakeBatchResponse:
        text = f'"{station.id}","I-35, Austin, TX","Match","Exact","I-35, Austin, TX","-97.743100,30.267200","1","L"\n'

        def raise_for_status(self):
            return None

    def fake_post(url, data, files, timeout):
        calls.append((url, data, files, timeout))
        return FakeBatchResponse()

    monkeypatch.setattr("routing.services.geocoding.requests.post", fake_post)

    results = CensusBatchStationGeocoder(timeout=3).geocode_stations([station])

    assert results == [
        StationGeocodeResult(
            station_id=str(station.id),
            matched=True,
            latitude=Decimal("30.267200"),
            longitude=Decimal("-97.743100"),
            score=None,
        )
    ]
    assert calls == [
        (
            "https://example.test/geocoder/locations/addressbatch",
            {"benchmark": "Public_AR_Current"},
            {
                "addressFile": (
                    "stations.csv",
                    f'{station.id},I-35,Austin,TX,\r\n',
                    "text/csv",
                )
            },
            3,
        )
    ]


@pytest.mark.django_db
def test_census_batch_station_geocoder_rejects_missing_response_id(monkeypatch, settings):
    from fuel.models import FuelStation

    settings.CENSUS_GEOCODER_BASE_URL = "https://example.test/geocoder"
    first = FuelStation.objects.create(
        opis_truckstop_id="123",
        name="Austin Fuel",
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.249"),
        source_row_hash="missing-response-first",
    )
    second = FuelStation.objects.create(
        opis_truckstop_id="124",
        name="Dallas Fuel",
        address="I-45",
        city="Dallas",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.249"),
        source_row_hash="missing-response-second",
    )

    class FakeBatchResponse:
        text = f'"{first.id}","I-35, Austin, TX","Match","Exact","I-35, Austin, TX","-97.743100,30.267200","1","L"\n'

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "routing.services.geocoding.requests.post",
        lambda *args, **kwargs: FakeBatchResponse(),
    )

    with pytest.raises(RoutingProviderError, match="missing submitted station IDs"):
        CensusBatchStationGeocoder().geocode_stations([first, second])


@pytest.mark.django_db
def test_census_batch_station_geocoder_rejects_unknown_response_id(monkeypatch, settings):
    from fuel.models import FuelStation

    settings.CENSUS_GEOCODER_BASE_URL = "https://example.test/geocoder"
    station = FuelStation.objects.create(
        opis_truckstop_id="123",
        name="Austin Fuel",
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.249"),
        source_row_hash="unknown-response-station",
    )

    class FakeBatchResponse:
        text = '"999999","I-35, Austin, TX","Match","Exact","I-35, Austin, TX","-97.743100,30.267200","1","L"\n'

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "routing.services.geocoding.requests.post",
        lambda *args, **kwargs: FakeBatchResponse(),
    )

    with pytest.raises(RoutingProviderError, match="unknown station IDs"):
        CensusBatchStationGeocoder().geocode_stations([station])


@pytest.mark.django_db
def test_census_batch_station_geocoder_rejects_duplicate_response_id(monkeypatch, settings):
    from fuel.models import FuelStation

    settings.CENSUS_GEOCODER_BASE_URL = "https://example.test/geocoder"
    station = FuelStation.objects.create(
        opis_truckstop_id="123",
        name="Austin Fuel",
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.249"),
        source_row_hash="duplicate-response-station",
    )

    class FakeBatchResponse:
        text = (
            f'"{station.id}","I-35, Austin, TX","Match","Exact","I-35, Austin, TX","-97.743100,30.267200","1","L"\n'
            f'"{station.id}","I-35, Austin, TX","Match","Exact","I-35, Austin, TX","-97.743100,30.267200","1","L"\n'
        )

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "routing.services.geocoding.requests.post",
        lambda *args, **kwargs: FakeBatchResponse(),
    )

    with pytest.raises(RoutingProviderError, match="duplicate station ID"):
        CensusBatchStationGeocoder().geocode_stations([station])


def test_census_batch_station_geocoder_maps_http_failure(monkeypatch):
    def fail_post(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setattr("routing.services.geocoding.requests.post", fail_post)

    with pytest.raises(RoutingProviderError, match="Census batch geocoder failed"):
        CensusBatchStationGeocoder().geocode_stations([])


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
