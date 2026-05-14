from decimal import Decimal

from routing.serializers import FuelPlanRequestSerializer


def test_fuel_plan_serializer_accepts_coordinates():
    serializer = FuelPlanRequestSerializer(
        data={
            "start": {"lat": 30.2672, "lng": -97.7431},
            "destination": {"lat": 39.7392, "lng": -104.9903},
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["start"] == {
        "lat": Decimal("30.267200"),
        "lng": Decimal("-97.743100"),
    }
    assert serializer.validated_data["max_range_miles"] == 500
    assert serializer.validated_data["miles_per_gallon"] == Decimal("10.00")
    assert serializer.validated_data["corridor_miles"] == 10


def test_fuel_plan_serializer_accepts_strings():
    serializer = FuelPlanRequestSerializer(
        data={"start": "  Austin, TX ", "destination": "Denver, CO"}
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["start"] == "Austin, TX"


def test_fuel_plan_serializer_rejects_invalid_corridor():
    serializer = FuelPlanRequestSerializer(
        data={"start": "Austin, TX", "destination": "Denver, CO", "corridor_miles": 99}
    )

    assert not serializer.is_valid()
    assert "corridor_miles" in serializer.errors


def test_fuel_plan_serializer_rejects_coordinates_outside_usa_bounds():
    serializer = FuelPlanRequestSerializer(
        data={
            "start": {"lat": 48.8566, "lng": 2.3522},
            "destination": {"lat": 39.7392, "lng": -104.9903},
        }
    )

    assert not serializer.is_valid()
    assert "start" in serializer.errors


def test_fuel_plan_serializer_rejects_empty_string_location():
    serializer = FuelPlanRequestSerializer(
        data={"start": "   ", "destination": "Denver, CO"}
    )

    assert not serializer.is_valid()
    assert "start" in serializer.errors


def test_fuel_plan_serializer_rejects_invalid_mpg():
    serializer = FuelPlanRequestSerializer(
        data={
            "start": "Austin, TX",
            "destination": "Denver, CO",
            "miles_per_gallon": 0,
        }
    )

    assert not serializer.is_valid()
    assert "miles_per_gallon" in serializer.errors
