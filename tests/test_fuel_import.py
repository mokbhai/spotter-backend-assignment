from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError

from fuel.models import FuelStation, LocationCache
from routing.exceptions import RoutingProviderError
from routing.services.fuel_import import (
    FuelPriceRow,
    import_fuel_price_rows,
    parse_fuel_price_csv,
    row_hash,
)
from routing.services.geocoding import StationGeocodeResult


@pytest.mark.django_db
def test_fuel_station_allows_duplicate_opis_ids():
    FuelStation.objects.create(
        opis_truckstop_id="20",
        name="PILOT TRAVEL CENTER #1243",
        address="I-8, EXIT 119 & SR-85",
        city="Gila Bend",
        state="AZ",
        rack_id="930",
        retail_price=Decimal("3.899"),
        source_row_hash="hash-one",
        is_active=False,
    )
    FuelStation.objects.create(
        opis_truckstop_id="20",
        name="PILOT #1243",
        address="I-8, EXIT 119 & SR-85",
        city="Gila Bend",
        state="AZ",
        rack_id="930",
        retail_price=Decimal("3.899"),
        source_row_hash="hash-two",
        is_active=False,
    )

    assert FuelStation.objects.filter(opis_truckstop_id="20").count() == 2


@pytest.mark.django_db
def test_fuel_station_source_row_hash_is_unique():
    FuelStation.objects.create(
        opis_truckstop_id="20",
        name="PILOT TRAVEL CENTER #1243",
        address="I-8, EXIT 119 & SR-85",
        city="Gila Bend",
        state="AZ",
        rack_id="930",
        retail_price=Decimal("3.899"),
        source_row_hash="same-hash",
    )

    with pytest.raises(IntegrityError):
        FuelStation.objects.create(
            opis_truckstop_id="21",
            name="PILOT OTHER",
            address="I-8",
            city="Gila Bend",
            state="AZ",
            rack_id="930",
            retail_price=Decimal("3.899"),
            source_row_hash="same-hash",
        )


@pytest.mark.django_db
def test_fuel_station_preserves_source_retail_price_precision():
    retail_price = Decimal("3.00733333")
    station = FuelStation(
        opis_truckstop_id="20",
        name="PILOT TRAVEL CENTER #1243",
        address="I-8, EXIT 119 & SR-85",
        city="Gila Bend",
        state="AZ",
        rack_id="930",
        retail_price=retail_price,
        source_row_hash="precise-price",
    )

    station.full_clean()
    station.save()
    station.refresh_from_db()

    assert station.retail_price == retail_price


@pytest.mark.django_db
def test_fuel_station_uses_import_default_state():
    station = FuelStation.objects.create(
        opis_truckstop_id="20",
        name="PILOT TRAVEL CENTER #1243",
        address="I-8, EXIT 119 & SR-85",
        city="Gila Bend",
        state="AZ",
        rack_id="930",
        retail_price=Decimal("3.899"),
        source_row_hash="default-state",
    )

    assert station.is_active is False
    assert station.geocoding_status == FuelStation.GeocodingStatus.PENDING
    assert station.latitude is None
    assert station.longitude is None


@pytest.mark.django_db
def test_location_cache_query_is_unique():
    LocationCache.objects.create(
        query="austin, tx",
        latitude=Decimal("30.2672"),
        longitude=Decimal("-97.7431"),
    )

    with pytest.raises(IntegrityError):
        LocationCache.objects.create(
            query="austin, tx",
            latitude=Decimal("30.2672"),
            longitude=Decimal("-97.7431"),
        )


def test_parse_fuel_price_csv_normalizes_rows(tmp_path):
    path = tmp_path / "fuel.csv"
    path.write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "79,DELAWARE TRUCK PLAZA,US-13 & US-40,New Castle                              ,de,243,3.249\n",
        encoding="utf-8",
    )

    rows = list(parse_fuel_price_csv(path))

    assert rows == [
        FuelPriceRow(
            opis_truckstop_id="79",
            name="DELAWARE TRUCK PLAZA",
            address="US-13 & US-40",
            city="New Castle",
            state="DE",
            rack_id="243",
            retail_price=Decimal("3.249"),
        )
    ]


def test_parse_fuel_price_csv_preserves_price_precision(tmp_path):
    path = tmp_path / "fuel.csv"
    path.write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "7,WOODSHED OF BIG CABIN,US-69,Big Cabin,OK,307,3.00733333\n",
        encoding="utf-8",
    )

    row = list(parse_fuel_price_csv(path))[0]

    assert row.retail_price == Decimal("3.00733333")


def test_parse_fuel_price_csv_handles_utf8_bom(tmp_path):
    path = tmp_path / "fuel.csv"
    path.write_text(
        "\ufeffOPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "7,WOODSHED OF BIG CABIN,US-69,Big Cabin,OK,307,3.00733333\n",
        encoding="utf-8",
    )

    row = list(parse_fuel_price_csv(path))[0]

    assert row.opis_truckstop_id == "7"
    assert row.retail_price == Decimal("3.00733333")


@pytest.mark.django_db
def test_import_fuel_price_rows_is_idempotent():
    row = FuelPriceRow(
        opis_truckstop_id="79",
        name="DELAWARE TRUCK PLAZA",
        address="US-13 & US-40",
        city="New Castle",
        state="DE",
        rack_id="243",
        retail_price=Decimal("3.249"),
    )

    first = import_fuel_price_rows([row])
    second = import_fuel_price_rows([row])

    assert first.created == 1
    assert first.updated == 0
    assert second.created == 0
    assert second.updated == 1
    assert FuelStation.objects.count() == 1


@pytest.mark.django_db
def test_import_fuel_price_rows_counts_duplicate_opis_ids():
    rows = [
        FuelPriceRow("20", "PILOT A", "I-8", "Gila Bend", "AZ", "930", Decimal("3.899")),
        FuelPriceRow("20", "PILOT B", "I-10", "Gila Bend", "AZ", "931", Decimal("3.899")),
    ]

    summary = import_fuel_price_rows(rows)

    assert summary.total_rows == 2
    assert summary.created == 2
    assert summary.duplicate_opis_ids == 1
    assert FuelStation.objects.filter(opis_truckstop_id="20").count() == 2


@pytest.mark.django_db
def test_import_fuel_price_rows_updates_existing_station_when_name_changes():
    original = FuelPriceRow(
        "79",
        "DELAWARE TRUCK PLAZA",
        "US-13 & US-40",
        "New Castle",
        "DE",
        "243",
        Decimal("3.249"),
    )
    renamed = FuelPriceRow(
        "79",
        "DELAWARE PLAZA",
        "US-13 & US-40",
        "New Castle",
        "DE",
        "243",
        Decimal("3.249"),
    )

    import_fuel_price_rows([original])
    station = FuelStation.objects.get()
    original_hash = station.source_row_hash
    station.geocoding_status = FuelStation.GeocodingStatus.MATCHED
    station.latitude = Decimal("39.662000")
    station.longitude = Decimal("-75.566000")
    station.geocoding_score = Decimal("100.000")
    station.is_active = True
    station.save()

    summary = import_fuel_price_rows([renamed])
    station.refresh_from_db()

    assert summary.created == 0
    assert summary.updated == 1
    assert FuelStation.objects.count() == 1
    assert station.name == "DELAWARE PLAZA"
    assert station.source_row_hash != original_hash
    assert station.source_row_hash == row_hash(renamed)
    assert station.geocoding_status == FuelStation.GeocodingStatus.MATCHED
    assert station.latitude == Decimal("39.662000")
    assert station.longitude == Decimal("-75.566000")
    assert station.geocoding_score == Decimal("100.000")
    assert station.is_active is True


@pytest.mark.django_db
def test_import_fuel_price_rows_updates_existing_station_when_price_changes():
    original = FuelPriceRow(
        "79",
        "DELAWARE TRUCK PLAZA",
        "US-13 & US-40",
        "New Castle",
        "DE",
        "243",
        Decimal("3.249"),
    )
    changed = FuelPriceRow(
        "79",
        "DELAWARE TRUCK PLAZA",
        "US-13 & US-40",
        "New Castle",
        "DE",
        "243",
        Decimal("3.349"),
    )

    import_fuel_price_rows([original])
    station = FuelStation.objects.get()
    original_hash = station.source_row_hash
    station.geocoding_status = FuelStation.GeocodingStatus.MATCHED
    station.latitude = Decimal("39.662000")
    station.longitude = Decimal("-75.566000")
    station.geocoding_score = Decimal("100.000")
    station.is_active = True
    station.save()

    summary = import_fuel_price_rows([changed])
    station.refresh_from_db()

    assert summary.created == 0
    assert summary.updated == 1
    assert FuelStation.objects.count() == 1
    assert station.retail_price == Decimal("3.349")
    assert station.source_row_hash != original_hash
    assert station.source_row_hash == row_hash(changed)
    assert station.geocoding_status == FuelStation.GeocodingStatus.MATCHED
    assert station.latitude == Decimal("39.662000")
    assert station.longitude == Decimal("-75.566000")
    assert station.geocoding_score == Decimal("100.000")
    assert station.is_active is True


@pytest.mark.django_db
def test_import_fuel_price_rows_handles_exact_duplicates_in_same_batch():
    row = FuelPriceRow("79", "A", "Addr", "City", "DE", "243", Decimal("3.249"))

    summary = import_fuel_price_rows([row, row])

    assert summary.total_rows == 2
    assert summary.created == 1
    assert summary.updated == 0
    assert summary.duplicate_opis_ids == 1
    assert FuelStation.objects.count() == 1


@pytest.mark.django_db
def test_import_fuel_price_rows_rolls_back_batch_on_error(monkeypatch):
    rows = [
        FuelPriceRow("91", "FIRST", "A", "City", "TX", "1", Decimal("3.100")),
        FuelPriceRow("92", "SECOND", "B", "City", "TX", "1", Decimal("3.200")),
    ]
    original_update_or_create = FuelStation.objects.update_or_create
    calls = 0

    def fail_after_first(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise IntegrityError("forced failure")
        return original_update_or_create(*args, **kwargs)

    monkeypatch.setattr(FuelStation.objects, "update_or_create", fail_after_first)

    with pytest.raises(IntegrityError):
        import_fuel_price_rows(rows)

    assert FuelStation.objects.filter(opis_truckstop_id__in=["91", "92"]).count() == 0


def test_row_hash_changes_when_source_data_changes():
    original = FuelPriceRow("79", "A", "Addr", "City", "DE", "243", Decimal("3.249"))
    changed = FuelPriceRow("79", "A", "Addr", "City", "DE", "243", Decimal("3.250"))

    assert row_hash(original) != row_hash(changed)


def test_row_hash_is_delimiter_safe():
    left = FuelPriceRow("79|A", "B", "Addr", "City", "DE", "243", Decimal("3.249"))
    right = FuelPriceRow("79", "A|B", "Addr", "City", "DE", "243", Decimal("3.249"))

    assert row_hash(left) != row_hash(right)


@pytest.mark.django_db
def test_import_command_loads_csv_without_live_geocoding(tmp_path, capsys):
    path = tmp_path / "fuel.csv"
    path.write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "79,DELAWARE TRUCK PLAZA,US-13 & US-40,New Castle,DE,243,3.249\n",
        encoding="utf-8",
    )

    call_command("import_fuel_prices", str(path), "--skip-geocoding")

    station = FuelStation.objects.get(opis_truckstop_id="79")
    assert station.is_active is False
    assert station.geocoding_status == FuelStation.GeocodingStatus.PENDING
    output = capsys.readouterr().out
    assert "total=1" in output
    assert "Skipped station geocoding" in output


@pytest.mark.django_db
def test_import_command_can_apply_batch_geocoding(tmp_path, capsys, monkeypatch):
    path = tmp_path / "fuel.csv"
    path.write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "79,DELAWARE TRUCK PLAZA,US-13 & US-40,New Castle,DE,243,3.249\n",
        encoding="utf-8",
    )
    geocode_calls = []

    class FakeBatchGeocoder:
        def geocode_stations(self, stations):
            geocode_calls.append(list(stations))
            return [
                StationGeocodeResult(
                    station_id=str(stations[0].id),
                    matched=True,
                    latitude=Decimal("39.662000"),
                    longitude=Decimal("-75.566000"),
                    score=Decimal("1"),
                )
            ]

    monkeypatch.setattr(
        "fuel.management.commands.import_fuel_prices.CensusBatchStationGeocoder",
        FakeBatchGeocoder,
    )

    call_command("import_fuel_prices", str(path))

    station = FuelStation.objects.get(opis_truckstop_id="79")
    assert len(geocode_calls) == 1
    assert geocode_calls[0] == [station]
    assert station.is_active is True
    assert station.geocoding_status == FuelStation.GeocodingStatus.MATCHED
    assert station.latitude == Decimal("39.662000")
    assert station.longitude == Decimal("-75.566000")
    output = capsys.readouterr().out
    assert "total=1" in output
    assert "Station geocoding summary: matched=1 unmatched=0 failed=0" in output


@pytest.mark.django_db
def test_import_command_reports_no_pending_stations(tmp_path, capsys):
    path = tmp_path / "fuel.csv"
    path.write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n",
        encoding="utf-8",
    )
    FuelStation.objects.create(
        opis_truckstop_id="79",
        name="DELAWARE TRUCK PLAZA",
        address="US-13 & US-40",
        city="New Castle",
        state="DE",
        rack_id="243",
        retail_price=Decimal("3.249"),
        source_row_hash="matched-before-command",
        geocoding_status=FuelStation.GeocodingStatus.MATCHED,
        latitude=Decimal("39.662000"),
        longitude=Decimal("-75.566000"),
        is_active=True,
    )

    call_command("import_fuel_prices", str(path))

    output = capsys.readouterr().out
    assert "total=0" in output
    assert "No pending stations to geocode." in output


@pytest.mark.django_db
def test_import_command_maps_batch_provider_error_to_command_error(tmp_path, monkeypatch):
    path = tmp_path / "fuel.csv"
    path.write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "79,DELAWARE TRUCK PLAZA,US-13 & US-40,New Castle,DE,243,3.249\n",
        encoding="utf-8",
    )

    class FailingBatchGeocoder:
        def geocode_stations(self, stations):
            raise RoutingProviderError("provider unavailable")

    monkeypatch.setattr(
        "fuel.management.commands.import_fuel_prices.CensusBatchStationGeocoder",
        FailingBatchGeocoder,
    )

    with pytest.raises(CommandError, match="Station batch geocoding failed: provider unavailable"):
        call_command("import_fuel_prices", str(path))
