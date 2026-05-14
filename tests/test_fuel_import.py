from decimal import Decimal

import pytest
from django.db import IntegrityError

from fuel.models import FuelStation, LocationCache
from routing.services.fuel_import import (
    FuelPriceRow,
    import_fuel_price_rows,
    parse_fuel_price_csv,
    row_hash,
)


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
        FuelPriceRow("20", "PILOT B", "I-8", "Gila Bend", "AZ", "930", Decimal("3.899")),
    ]

    summary = import_fuel_price_rows(rows)

    assert summary.total_rows == 2
    assert summary.created == 2
    assert summary.duplicate_opis_ids == 1
    assert FuelStation.objects.filter(opis_truckstop_id="20").count() == 2


def test_row_hash_changes_when_source_data_changes():
    original = FuelPriceRow("79", "A", "Addr", "City", "DE", "243", Decimal("3.249"))
    changed = FuelPriceRow("79", "A", "Addr", "City", "DE", "243", Decimal("3.250"))

    assert row_hash(original) != row_hash(changed)
