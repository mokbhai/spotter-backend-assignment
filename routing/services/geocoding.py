from dataclasses import dataclass
from decimal import Decimal, DecimalException
from typing import Protocol

import requests
from django.conf import settings

from routing.exceptions import LocationNotFoundError, RoutingProviderError


@dataclass(frozen=True)
class GeocodedLocation:
    query: str
    latitude: Decimal
    longitude: Decimal
    provider: str
    raw_response: dict


class SingleGeocoder(Protocol):
    def geocode_one(self, query: str) -> GeocodedLocation | None:
        ...


def normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


class CensusGeocoder:
    provider = "census"

    def __init__(self, timeout: float | None = None):
        self.timeout = timeout or getattr(settings, "CENSUS_GEOCODER_TIMEOUT", 10)

    def geocode_one(self, query: str) -> GeocodedLocation | None:
        try:
            response = requests.get(
                f"{settings.CENSUS_GEOCODER_BASE_URL}/locations/onelineaddress",
                params={
                    "address": query,
                    "benchmark": "Public_AR_Current",
                    "format": "json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            matches = payload.get("result", {}).get("addressMatches", [])
            if not matches:
                return None

            match = matches[0]
            coordinates = match["coordinates"]
            return GeocodedLocation(
                query=query,
                latitude=Decimal(str(coordinates["y"])),
                longitude=Decimal(str(coordinates["x"])),
                provider=self.provider,
                raw_response=match,
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            DecimalException,
            requests.RequestException,
        ) as exc:
            raise RoutingProviderError("Census geocoder failed") from exc


def resolve_location(query: str, provider: SingleGeocoder | None = None) -> GeocodedLocation:
    from fuel.models import LocationCache

    normalized_query = normalize_query(query)
    if not normalized_query:
        raise LocationNotFoundError("Location query cannot be blank")

    cached = LocationCache.objects.filter(query=normalized_query).first()
    if cached:
        return GeocodedLocation(
            query=cached.query,
            latitude=cached.latitude,
            longitude=cached.longitude,
            provider=cached.provider,
            raw_response=cached.raw_response,
        )

    geocoder = provider or CensusGeocoder()
    location = geocoder.geocode_one(query)
    if location is None:
        raise LocationNotFoundError(f"No geocoding match found for {query!r}")

    LocationCache.objects.update_or_create(
        query=normalized_query,
        defaults={
            "latitude": location.latitude,
            "longitude": location.longitude,
            "provider": location.provider,
            "raw_response": location.raw_response,
        },
    )
    return GeocodedLocation(
        query=normalized_query,
        latitude=location.latitude,
        longitude=location.longitude,
        provider=location.provider,
        raw_response=location.raw_response,
    )
