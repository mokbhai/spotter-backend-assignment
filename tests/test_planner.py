from decimal import Decimal
from types import MappingProxyType

import pytest

from fuel.models import FuelStation, LocationCache
from routing.exceptions import (
    LocationNotFoundError,
    NoFeasibleFuelPlanError,
    RoutingProviderError,
)
from routing.services.osrm import Route
from routing.services.planner import build_route_fuel_plan


class FakeRouter:
    def __init__(self, route):
        self.route_result = route
        self.calls = []

    def route(self, start_lat, start_lng, dest_lat, dest_lng):
        self.calls.append((start_lat, start_lng, dest_lat, dest_lng))
        return self.route_result


class FailingRouter:
    def route(self, start_lat, start_lng, dest_lat, dest_lng):
        raise RoutingProviderError("Route calculation failed.")


def create_station(
    *,
    name="Austin Fuel",
    latitude=30,
    longitude=-97,
    retail_price=Decimal("3.25000000"),
    source_row_hash=None,
):
    return FuelStation.objects.create(
        opis_truckstop_id=name,
        name=name,
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="100",
        retail_price=retail_price,
        latitude=Decimal(str(latitude)),
        longitude=Decimal(str(longitude)),
        geocoding_status=FuelStation.GeocodingStatus.MATCHED,
        source_row_hash=source_row_hash or name,
        is_active=True,
    )


@pytest.mark.django_db
def test_planner_returns_route_and_fuel_plan_with_coordinate_inputs():
    station = create_station()
    route = Route(
        distance_miles=100,
        geometry={
            "type": "LineString",
            "coordinates": [[-97, 30], [-97, 31]],
        },
    )
    router = FakeRouter(route)

    response = build_route_fuel_plan(
        start={"lat": Decimal("30.000000"), "lng": Decimal("-97.000000")},
        destination={"lat": Decimal("31.000000"), "lng": Decimal("-97.000000")},
        corridor_miles=10,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
        router=router,
    )

    assert router.calls == [
        (
            Decimal("30.000000"),
            Decimal("-97.000000"),
            Decimal("31.000000"),
            Decimal("-97.000000"),
        )
    ]
    assert response["route"] == {
        "distance_miles": 100,
        "geometry": route.geometry,
    }
    assert response["fuel_plan"]["total_gallons"] == Decimal("10.00")
    assert response["fuel_plan"]["total_cost"] == Decimal("32.50")
    assert response["fuel_plan"]["currency"] == "USD"
    assert response["fuel_plan"]["max_range_miles"] == 500
    assert response["fuel_plan"]["miles_per_gallon"] == Decimal("10")
    assert response["fuel_plan"]["stops"] == [
        {
            "station_id": station.id,
            "name": "Austin Fuel",
            "address": "I-35",
            "city": "Austin",
            "state": "TX",
            "lat": Decimal("30.000000"),
            "lng": Decimal("-97.000000"),
            "price_per_gallon": Decimal("3.25000000"),
            "route_mile": 0,
            "gallons": Decimal("10.00"),
            "cost": Decimal("32.50"),
        }
    ]
    assert response["warnings"] == []
    assert response["metadata"] == {"routing_provider": "osrm"}


@pytest.mark.django_db
def test_planner_accepts_generic_mapping_coordinate_inputs():
    create_station()
    route = Route(
        distance_miles=100,
        geometry={
            "type": "LineString",
            "coordinates": [[-97, 30], [-97, 31]],
        },
    )
    router = FakeRouter(route)

    build_route_fuel_plan(
        start=MappingProxyType(
            {"lat": Decimal("30.000000"), "lng": Decimal("-97.000000")}
        ),
        destination=MappingProxyType(
            {"lat": Decimal("31.000000"), "lng": Decimal("-97.000000")}
        ),
        corridor_miles=10,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
        router=router,
    )

    assert router.calls == [
        (
            Decimal("30.000000"),
            Decimal("-97.000000"),
            Decimal("31.000000"),
            Decimal("-97.000000"),
        )
    ]


@pytest.mark.django_db
def test_planner_resolves_string_locations_from_cache_or_provider():
    LocationCache.objects.create(
        query="austin, tx",
        latitude=Decimal("30.267200"),
        longitude=Decimal("-97.743100"),
        provider="test",
    )
    LocationCache.objects.create(
        query="dallas, tx",
        latitude=Decimal("32.776700"),
        longitude=Decimal("-96.797000"),
        provider="test",
    )
    create_station(latitude=30.2672, longitude=-97.7431)
    route = Route(
        distance_miles=100,
        geometry={
            "type": "LineString",
            "coordinates": [[-97.7431, 30.2672], [-96.797, 32.7767]],
        },
    )
    router = FakeRouter(route)

    build_route_fuel_plan(
        start="Austin, TX",
        destination="Dallas, TX",
        corridor_miles=10,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
        router=router,
    )

    assert router.calls == [
        (
            Decimal("30.267200"),
            Decimal("-97.743100"),
            Decimal("32.776700"),
            Decimal("-96.797000"),
        )
    ]


@pytest.mark.django_db
def test_planner_propagates_location_resolution_failure(monkeypatch):
    def fail_resolve_location(query):
        raise LocationNotFoundError(f"No geocoding match found for {query!r}")

    monkeypatch.setattr("routing.services.planner.resolve_location", fail_resolve_location)

    with pytest.raises(LocationNotFoundError, match="No geocoding match"):
        build_route_fuel_plan(
            start="Missing Place",
            destination={"lat": Decimal("31.000000"), "lng": Decimal("-97.000000")},
            corridor_miles=10,
            max_range_miles=500,
            miles_per_gallon=Decimal("10"),
            router=FakeRouter(
                Route(
                    distance_miles=100,
                    geometry={
                        "type": "LineString",
                        "coordinates": [[-97, 30], [-97, 31]],
                    },
                )
            ),
        )


@pytest.mark.django_db
def test_planner_propagates_router_failure():
    with pytest.raises(RoutingProviderError, match="Route calculation failed"):
        build_route_fuel_plan(
            start={"lat": Decimal("30.000000"), "lng": Decimal("-97.000000")},
            destination={"lat": Decimal("31.000000"), "lng": Decimal("-97.000000")},
            corridor_miles=10,
            max_range_miles=500,
            miles_per_gallon=Decimal("10"),
            router=FailingRouter(),
        )


@pytest.mark.django_db
def test_planner_raises_no_feasible_when_no_candidate_station():
    route = Route(
        distance_miles=100,
        geometry={
            "type": "LineString",
            "coordinates": [[-97, 30], [-97, 31]],
        },
    )

    with pytest.raises(NoFeasibleFuelPlanError):
        build_route_fuel_plan(
            start={"lat": Decimal("30.000000"), "lng": Decimal("-97.000000")},
            destination={"lat": Decimal("31.000000"), "lng": Decimal("-97.000000")},
            corridor_miles=10,
            max_range_miles=500,
            miles_per_gallon=Decimal("10"),
            router=FakeRouter(route),
        )


@pytest.mark.django_db
def test_planner_rounds_route_distance_and_stop_route_mile():
    create_station(latitude=30.1, longitude=-97)
    route = Route(
        distance_miles=100.126,
        geometry={
            "type": "LineString",
            "coordinates": [[-97, 30], [-97, 31]],
        },
    )

    response = build_route_fuel_plan(
        start={"lat": Decimal("30.000000"), "lng": Decimal("-97.000000")},
        destination={"lat": Decimal("31.000000"), "lng": Decimal("-97.000000")},
        corridor_miles=10,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
        router=FakeRouter(route),
    )

    assert response["route"]["distance_miles"] == 100.13
    assert response["fuel_plan"]["stops"][0]["route_mile"] == 6.91
