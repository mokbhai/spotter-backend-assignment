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


def test_fuel_plan_serializer_trims_destination_string():
    serializer = FuelPlanRequestSerializer(
        data={"start": "Austin, TX", "destination": "  Denver, CO  "}
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["destination"] == "Denver, CO"


def test_fuel_plan_serializer_rejects_too_long_location_string():
    serializer = FuelPlanRequestSerializer(
        data={"start": f" {'a' * 256} ", "destination": "Denver, CO"}
    )

    assert not serializer.is_valid()
    assert "start" in serializer.errors


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


def test_fuel_plan_serializer_uses_request_settings(settings):
    settings.DEFAULT_ROUTE_CORRIDOR_MILES = 7
    settings.MAX_ROUTE_CORRIDOR_MILES = 12
    settings.DEFAULT_MAX_RANGE_MILES = 300
    settings.DEFAULT_MILES_PER_GALLON = Decimal("8.50")

    serializer = FuelPlanRequestSerializer(
        data={"start": "Austin, TX", "destination": "Denver, CO"}
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["corridor_miles"] == 7
    assert serializer.validated_data["max_range_miles"] == 300
    assert serializer.validated_data["miles_per_gallon"] == Decimal("8.50")

    invalid_serializer = FuelPlanRequestSerializer(
        data={
            "start": "Austin, TX",
            "destination": "Denver, CO",
            "corridor_miles": 13,
        }
    )

    assert not invalid_serializer.is_valid()
    assert "corridor_miles" in invalid_serializer.errors


def test_fuel_plan_serializer_rejects_max_range_above_setting(settings):
    settings.DEFAULT_MAX_RANGE_MILES = 300

    serializer = FuelPlanRequestSerializer(
        data={
            "start": "Austin, TX",
            "destination": "Denver, CO",
            "max_range_miles": 301,
        }
    )

    assert not serializer.is_valid()
    assert "max_range_miles" in serializer.errors
