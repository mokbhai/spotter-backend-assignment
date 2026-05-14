from collections.abc import Mapping
from decimal import Decimal

from rest_framework import serializers


class CoordinateSerializer(serializers.Serializer):
    lat = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-90"),
        max_value=Decimal("90"),
    )
    lng = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-180"),
        max_value=Decimal("180"),
    )

    def validate(self, attrs):
        lat = attrs["lat"]
        lng = attrs["lng"]

        if not (Decimal("18") <= lat <= Decimal("72")):
            raise serializers.ValidationError(
                {"lat": "Latitude must be within broad USA bounds."}
            )
        if not (Decimal("-170") <= lng <= Decimal("-66")):
            raise serializers.ValidationError(
                {"lng": "Longitude must be within broad USA bounds."}
            )

        return attrs


class LocationField(serializers.Field):
    default_error_messages = {
        "blank": "Location must not be blank.",
        "invalid": "Location must be a string or coordinate object.",
    }

    def to_internal_value(self, data):
        if isinstance(data, str):
            value = data.strip()
            if not value:
                self.fail("blank")
            return value

        if isinstance(data, Mapping):
            serializer = CoordinateSerializer(data=data)
            if not serializer.is_valid():
                raise serializers.ValidationError(serializer.errors)
            return dict(serializer.validated_data)

        self.fail("invalid")

    def to_representation(self, value):
        return value


class FuelPlanRequestSerializer(serializers.Serializer):
    start = LocationField()
    destination = LocationField()
    corridor_miles = serializers.IntegerField(default=10, min_value=1, max_value=25)
    max_range_miles = serializers.IntegerField(default=500, min_value=1, max_value=500)
    miles_per_gallon = serializers.DecimalField(
        default=Decimal("10.00"),
        max_digits=6,
        decimal_places=2,
        min_value=Decimal("1"),
    )
