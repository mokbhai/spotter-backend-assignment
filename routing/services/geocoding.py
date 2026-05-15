import csv
from dataclasses import dataclass
from decimal import Decimal, DecimalException
from functools import lru_cache
from io import StringIO
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


@dataclass(frozen=True)
class CityStateLocation:
    latitude: Decimal
    longitude: Decimal


@dataclass(frozen=True)
class CityStateGeocodingSummary:
    approximated: int
    unmatched: int


class SingleGeocoder(Protocol):
    def geocode_one(self, query: str) -> GeocodedLocation | None:
        ...


CITY_STATE_PROVIDER = "geonames_city_state"


def normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def normalize_city_name(city: str) -> str:
    return " ".join(city.casefold().replace(".", "").split())


def parse_city_state_query(query: str) -> tuple[str, str] | None:
    parts = [part.strip() for part in query.split(",")]
    if len(parts) != 2:
        return None

    city, state = parts
    state_code = state.upper()
    if not city or len(state_code) != 2 or not state_code.isalpha():
        return None

    return city, state_code


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
        seen_station_ids = set()
        for row in reader:
            if not row:
                continue
            if len(row) < 3:
                raise ValueError("Census batch row has too few columns")

            station_id = row[0]
            if station_id in seen_station_ids:
                raise RoutingProviderError(
                    f"Census batch geocoder returned duplicate station ID: {station_id}"
                )
            seen_station_ids.add(station_id)

            status = row[2]
            if status in {"No_Match", "Tie"}:
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

            if len(row) < 6:
                raise ValueError("Census batch match row has too few columns")

            coordinate_parts = row[5].split(",")
            if len(coordinate_parts) != 2:
                raise ValueError("Census batch match row has malformed coordinates")

            longitude = Decimal(coordinate_parts[0])
            latitude = Decimal(coordinate_parts[1])
            results.append(
                StationGeocodeResult(
                    station_id=station_id,
                    matched=True,
                    latitude=latitude,
                    longitude=longitude,
                    score=None,
                )
            )
        return results
    except (csv.Error, DecimalException, IndexError, TypeError, ValueError) as exc:
        raise RoutingProviderError("Census batch geocoder returned malformed response") from exc


class CensusBatchStationGeocoder:
    def __init__(self, timeout: float | None = None):
        self.timeout = timeout or getattr(settings, "CENSUS_BATCH_GEOCODER_TIMEOUT", 60)

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
            results = parse_census_batch_response(response.text)
        except requests.RequestException as exc:
            raise RoutingProviderError("Census batch geocoder failed") from exc

        submitted_ids = {str(station.id) for station in stations}
        returned_ids = {result.station_id for result in results}
        unknown_ids = returned_ids - submitted_ids
        if unknown_ids:
            raise RoutingProviderError(
                "Census batch geocoder returned unknown station IDs: "
                f"{', '.join(sorted(unknown_ids))}"
            )
        missing_ids = submitted_ids - returned_ids
        if missing_ids:
            raise RoutingProviderError(
                "Census batch geocoder missing submitted station IDs: "
                f"{', '.join(sorted(missing_ids))}"
            )

        return results


class CityStateGeocoder:
    def __init__(self, cities: dict | None = None):
        self._city_index = self._build_city_index(cities)

    def geocode_city_state(self, city: str, state: str) -> CityStateLocation | None:
        city_record = self._city_index.get((normalize_city_name(city), state.upper()))
        if city_record is None:
            return None

        return CityStateLocation(
            latitude=Decimal(str(city_record["latitude"])).quantize(Decimal("0.000001")),
            longitude=Decimal(str(city_record["longitude"])).quantize(Decimal("0.000001")),
        )

    def _build_city_index(self, cities: dict | None):
        if cities is None:
            import geonamescache

            cities = geonamescache.GeonamesCache().get_cities()

        city_index = {}
        for city_record in cities.values():
            if city_record.get("countrycode") != "US":
                continue

            state = city_record.get("admin1code")
            names = {city_record.get("name", "")}
            names.update(city_record.get("alternatenames") or [])
            for name in names:
                key = (normalize_city_name(name), state)
                existing = city_index.get(key)
                if existing is None or _population(city_record) > _population(existing):
                    city_index[key] = city_record

        return city_index


def _population(city_record) -> int:
    return int(city_record.get("population") or 0)


@lru_cache(maxsize=1)
def get_city_state_geocoder() -> CityStateGeocoder:
    return CityStateGeocoder()


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
            if not _has_valid_station_coordinates(result.latitude, result.longitude):
                failed += 1
                continue

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


def apply_city_state_geocoding_fallback(
    stations,
    geocoder: CityStateGeocoder | None = None,
) -> CityStateGeocodingSummary:
    from fuel.models import FuelStation

    geocoder = geocoder or CityStateGeocoder()
    approximated = 0
    unmatched = 0

    for station in stations:
        location = geocoder.geocode_city_state(station.city, station.state)
        if location is None:
            unmatched += 1
            continue

        station.latitude = location.latitude
        station.longitude = location.longitude
        station.geocoding_score = None
        station.geocoding_status = FuelStation.GeocodingStatus.CITY_APPROXIMATE
        station.is_active = True
        station.save(
            update_fields=[
                "latitude",
                "longitude",
                "geocoding_score",
                "geocoding_status",
                "is_active",
            ]
        )
        approximated += 1

    return CityStateGeocodingSummary(approximated=approximated, unmatched=unmatched)


def _has_valid_station_coordinates(
    latitude: Decimal | None,
    longitude: Decimal | None,
) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and Decimal("-90") <= latitude <= Decimal("90")
        and Decimal("-180") <= longitude <= Decimal("180")
    )


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

    city_state = parse_city_state_query(query)
    if city_state is not None:
        city, state = city_state
        city_state_location = get_city_state_geocoder().geocode_city_state(city, state)
        if city_state_location is not None:
            raw_response = {
                "city": city,
                "state": state,
                "precision": "city_state",
            }
            LocationCache.objects.update_or_create(
                query=normalized_query,
                defaults={
                    "latitude": city_state_location.latitude,
                    "longitude": city_state_location.longitude,
                    "provider": CITY_STATE_PROVIDER,
                    "raw_response": raw_response,
                },
            )
            return GeocodedLocation(
                query=normalized_query,
                latitude=city_state_location.latitude,
                longitude=city_state_location.longitude,
                provider=CITY_STATE_PROVIDER,
                raw_response=raw_response,
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
