from django.db import models


class FuelStation(models.Model):
    class GeocodingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        MATCHED = "matched", "Matched"
        UNMATCHED = "unmatched", "Unmatched"
        FAILED = "failed", "Failed"

    opis_truckstop_id = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=8)
    rack_id = models.CharField(max_length=32)
    retail_price = models.DecimalField(max_digits=8, decimal_places=4)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    geocoding_status = models.CharField(
        max_length=16,
        choices=GeocodingStatus.choices,
        default=GeocodingStatus.PENDING,
    )
    geocoding_score = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
    )
    source_row_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["state", "city"]),
            models.Index(fields=["is_active", "latitude", "longitude"]),
            models.Index(fields=["retail_price"]),
            models.Index(fields=["opis_truckstop_id"]),
        ]
        ordering = ["name", "city", "state"]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"


class LocationCache(models.Model):
    query = models.CharField(max_length=255, unique=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    provider = models.CharField(max_length=64, default="census")
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["query"]

    def __str__(self):
        return self.query
