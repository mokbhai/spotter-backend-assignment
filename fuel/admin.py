from django.contrib import admin

from fuel.models import FuelStation, LocationCache


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "city",
        "state",
        "retail_price",
        "is_active",
        "geocoding_status",
    )
    list_filter = ("state", "is_active", "geocoding_status")
    search_fields = ("name", "city", "state", "opis_truckstop_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(LocationCache)
class LocationCacheAdmin(admin.ModelAdmin):
    list_display = ("query", "latitude", "longitude", "provider", "updated_at")
    search_fields = ("query",)
    readonly_fields = ("created_at", "updated_at")
