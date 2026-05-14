import csv
from io import StringIO
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


@dataclass(frozen=True)
class StationGeocodeResult:
    station_id: str
    matched: bool
    latitude: Decimal | None
    longitude: Decimal | None
    score: Decimal | None = None


@dataclass(frozen=True)
class StationGeocodingSummary:
    matched: int
    unmatched: int
    failed: int


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


def build_census_batch_input(stations) -> str:
    output = StringIO()
    writer = csv.writer(output)
    for station in stations:
        writer.writerow([station.id, station.address, station.city, station.state, ""])
    return output.getvalue()


def parse_census_batch_response(response_text: str) -> list[StationGeocodeResult]:
    try:
        reader = csv.reader(StringIO(response_text))
        results = []
        for row in reader:
            if not row:
                continue
            if len(row) < 6:
                raise ValueError("Census batch row has too few columns")

            station_id = row[0]
            status = row[2]
            if status == "No_Match":
                results.append(
                    StationGeocodeResult(
                        station_id=station_id,
                        matched=False,
                        latitude=None,
                        longitude=None,
                    )
                )
                continue

            if status != "Match":
                raise ValueError(f"Unsupported Census batch status: {status}")

            coordinate_parts = row[5].split(",")
            if len(coordinate_parts) != 2:
                raise ValueError("Census batch match row has malformed coordinates")

            longitude = Decimal(coordinate_parts[0])
            latitude = Decimal(coordinate_parts[1])
            score = Decimal(row[6]) if len(row) > 6 and row[6] else None
            results.append(
                StationGeocodeResult(
                    station_id=station_id,
                    matched=True,
                    latitude=latitude,
                    longitude=longitude,
                    score=score,
                )
            )
        return results
    except (csv.Error, DecimalException, IndexError, TypeError, ValueError) as exc:
        raise RoutingProviderError("Census batch geocoder returned malformed response") from exc


class CensusBatchStationGeocoder:
    def __init__(self, timeout: float | None = None):
        self.timeout = timeout or getattr(settings, "CENSUS_GEOCODER_TIMEOUT", 10)

    def geocode_stations(self, stations) -> list[StationGeocodeResult]:
        csv_content = build_census_batch_input(stations)
        try:
            response = requests.post(
                f"{settings.CENSUS_GEOCODER_BASE_URL}/locations/addressbatch",
                data={"benchmark": "Public_AR_Current"},
                files={
                    "addressFile": (
                        "stations.csv",
                        csv_content,
                        "text/csv",
                    )
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return parse_census_batch_response(response.text)
        except requests.RequestException as exc:
            raise RoutingProviderError("Census batch geocoder failed") from exc


def apply_station_geocoding_results(results) -> StationGeocodingSummary:
    from fuel.models import FuelStation

    matched = 0
    unmatched = 0
    failed = 0

    for result in results:
        try:
            station = FuelStation.objects.filter(pk=result.station_id).first()
        except (TypeError, ValueError):
            station = None
        if station is None:
            failed += 1
            continue

        if result.matched:
            station.latitude = result.latitude
            station.longitude = result.longitude
            station.geocoding_score = result.score
            station.geocoding_status = FuelStation.GeocodingStatus.MATCHED
            station.is_active = True
            matched += 1
        else:
            station.latitude = None
            station.longitude = None
            station.geocoding_score = None
            station.geocoding_status = FuelStation.GeocodingStatus.UNMATCHED
            station.is_active = False
            unmatched += 1

        station.save(
            update_fields=[
                "latitude",
                "longitude",
                "geocoding_score",
                "geocoding_status",
                "is_active",
            ]
        )

    return StationGeocodingSummary(matched=matched, unmatched=unmatched, failed=failed)


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
