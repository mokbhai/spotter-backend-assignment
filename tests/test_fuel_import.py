from decimal import Decimal

import pytest
from django.db import IntegrityError

from fuel.models import FuelStation, LocationCache


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
