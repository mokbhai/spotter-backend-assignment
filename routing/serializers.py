from collections.abc import Mapping
from decimal import Decimal

from django.conf import settings
from rest_framework import serializers


LOCATION_QUERY_MAX_LENGTH = 255


def _decimal_setting(name):
    return Decimal(str(getattr(settings, name))).quantize(Decimal("0.01"))


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
        "max_length": f"Location must be no more than {LOCATION_QUERY_MAX_LENGTH} characters.",
    }

    def to_internal_value(self, data):
        if isinstance(data, str):
            value = data.strip()
            if not value:
                self.fail("blank")
            if len(" ".join(value.split())) > LOCATION_QUERY_MAX_LENGTH:
                self.fail("max_length")
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["corridor_miles"] = serializers.IntegerField(
            default=settings.DEFAULT_ROUTE_CORRIDOR_MILES,
            min_value=1,
            max_value=settings.MAX_ROUTE_CORRIDOR_MILES,
        )
        self.fields["max_range_miles"] = serializers.IntegerField(
            default=settings.DEFAULT_MAX_RANGE_MILES,
            min_value=1,
            max_value=settings.DEFAULT_MAX_RANGE_MILES,
        )
        self.fields["miles_per_gallon"] = serializers.DecimalField(
            default=_decimal_setting("DEFAULT_MILES_PER_GALLON"),
            max_digits=6,
            decimal_places=2,
            min_value=Decimal("1"),
        )
