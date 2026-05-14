from decimal import Decimal

import pytest

from fuel.models import FuelStation
from routing.services.candidates import find_candidate_stations
from routing.services.geometry import (
    cumulative_route_miles,
    haversine_miles,
    project_point_to_route,
    route_points,
)


def create_station(
    *,
    name,
    latitude,
    longitude,
    is_active=True,
    source_row_hash=None,
):
    return FuelStation.objects.create(
        opis_truckstop_id=name,
        name=name,
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="100",
        retail_price=Decimal("3.499"),
        latitude=Decimal(str(latitude)) if latitude is not None else None,
        longitude=Decimal(str(longitude)) if longitude is not None else None,
        geocoding_status=FuelStation.GeocodingStatus.MATCHED,
        source_row_hash=source_row_hash or name,
        is_active=is_active,
    )


def test_haversine_miles_is_reasonable():
    distance = haversine_miles(30.2672, -97.7431, 30.2672, -98.7431)

    assert distance == pytest.approx(59.7, rel=0.05)


def test_route_points_rejects_invalid_geometry():
    with pytest.raises(ValueError):
        route_points({"type": "Point", "coordinates": [-97.0, 30.0]})


def test_cumulative_route_miles_starts_at_zero():
    totals = cumulative_route_miles([(30.0, -97.0), (30.0, -98.0), (31.0, -98.0)])

    assert totals[0] == 0
    assert totals[1] > 0
    assert totals[2] > totals[1]


def test_project_point_to_route_finds_nearest_segment():
    points = [(30.0, -97.0), (30.0, -98.0)]

    projection = project_point_to_route(30.0, -97.5, points)

    assert projection.distance_to_route_miles == pytest.approx(0, abs=0.5)
    assert projection.route_mile > 20


@pytest.mark.django_db
def test_find_candidate_stations_filters_by_route_corridor():
    near = create_station(
        name="near",
        latitude=30.2672,
        longitude=-97.7431,
    )
    create_station(
        name="far",
        latitude=32.7767,
        longitude=-96.7970,
    )
    create_station(
        name="inactive",
        latitude=30.2672,
        longitude=-97.7431,
        is_active=False,
    )
    route_geometry = {
        "type": "LineString",
        "coordinates": [[-97.7431, 30.2672], [-97.7431, 30.5]],
    }

    candidates = find_candidate_stations(route_geometry, corridor_miles=10)

    assert [candidate.station.id for candidate in candidates] == [near.id]
    assert candidates[0].route_mile == pytest.approx(0, abs=1)


@pytest.mark.django_db
def test_find_candidate_stations_sorts_candidates_by_route_mile():
    later = create_station(
        name="later",
        latitude=30.45,
        longitude=-97.7431,
    )
    earlier = create_station(
        name="earlier",
        latitude=30.30,
        longitude=-97.7431,
    )
    route_geometry = {
        "type": "LineString",
        "coordinates": [[-97.7431, 30.25], [-97.7431, 30.5]],
    }

    candidates = find_candidate_stations(route_geometry, corridor_miles=5)

    assert [candidate.station.id for candidate in candidates] == [earlier.id, later.id]
    assert candidates[0].route_mile < candidates[1].route_mile
