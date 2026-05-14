from dataclasses import dataclass
from numbers import Real

import requests
from django.conf import settings

from routing.exceptions import RoutingProviderError


METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class Route:
    distance_miles: float
    geometry: dict


class OSRMClient:
    def __init__(self, base_url: str | None = None, timeout: float = 15):
        self.base_url = (base_url or settings.OSRM_BASE_URL).rstrip("/")
        self.timeout = timeout

    def route(
        self,
        start_lat,
        start_lng,
        dest_lat,
        dest_lng,
    ) -> Route:
        url = (
            f"{self.base_url}/route/v1/driving/"
            f"{start_lng},{start_lat};{dest_lng},{dest_lat}"
        )
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
        }

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            route = self._extract_route(payload)
            geometry = route["geometry"]
            self._validate_geometry(geometry)
            return Route(
                distance_miles=float(route["distance"]) / METERS_PER_MILE,
                geometry=geometry,
            )
        except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
            raise RoutingProviderError("Route calculation failed.") from exc

    def _extract_route(self, payload):
        if not isinstance(payload, dict):
            raise RoutingProviderError("Route calculation failed.")

        if payload.get("code") != "Ok":
            raise RoutingProviderError("Route calculation failed.")

        routes = payload.get("routes")
        if not isinstance(routes, list) or not routes:
            raise RoutingProviderError("Route calculation failed.")

        return routes[0]

    def _validate_geometry(self, geometry):
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        if (
            not isinstance(geometry, dict)
            or geometry.get("type") != "LineString"
            or not isinstance(coordinates, list)
            or len(coordinates) < 2
        ):
            raise RoutingProviderError("Route calculation failed.")

        for position in coordinates:
            if (
                not isinstance(position, (list, tuple))
                or len(position) < 2
                or not self._is_numeric_coordinate(position[0])
                or not self._is_numeric_coordinate(position[1])
            ):
                raise RoutingProviderError("Route calculation failed.")

    def _is_numeric_coordinate(self, value):
        return isinstance(value, Real) and not isinstance(value, bool)
