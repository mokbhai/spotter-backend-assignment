from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from fuel.models import FuelStation
from routing.services.geometry import (
    cumulative_route_miles,
    downsample_route_points,
    expanded_bounding_box,
    project_point_to_route,
    route_points,
)


@dataclass(frozen=True)
class CandidateStation:
    station: FuelStation
    route_mile: float
    distance_to_route_miles: float


def find_candidate_stations(route_geometry, corridor_miles):
    points = route_points(route_geometry)
    min_lat, max_lat, min_lng, max_lng = expanded_bounding_box(points, corridor_miles)
    route_miles = cumulative_route_miles(points)
    corridor_miles = float(corridor_miles)
    projection_spacing_miles = min(
        getattr(settings, "ROUTE_CANDIDATE_PROJECTION_SPACING_MILES", 5),
        max(corridor_miles / 2, 0.25),
    )
    projection_points, projection_route_miles = downsample_route_points(
        points,
        route_miles,
        projection_spacing_miles,
    )
    candidates = []

    stations = FuelStation.objects.filter(
        is_active=True,
        latitude__isnull=False,
        longitude__isnull=False,
        latitude__gte=Decimal(str(min_lat)),
        latitude__lte=Decimal(str(max_lat)),
        longitude__gte=Decimal(str(min_lng)),
        longitude__lte=Decimal(str(max_lng)),
    )

    for station in stations:
        projection = project_point_to_route(
            float(station.latitude),
            float(station.longitude),
            projection_points,
            route_miles=projection_route_miles,
        )
        if projection.distance_to_route_miles <= corridor_miles:
            candidates.append(
                CandidateStation(
                    station=station,
                    route_mile=projection.route_mile,
                    distance_to_route_miles=projection.distance_to_route_miles,
                )
            )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.route_mile,
            candidate.distance_to_route_miles,
            candidate.station.retail_price,
            candidate.station.pk,
        ),
    )
