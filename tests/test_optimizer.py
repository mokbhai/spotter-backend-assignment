from decimal import Decimal

import pytest

from routing.exceptions import NoFeasibleFuelPlanError
from routing.services.optimizer import OptimizerStation, build_fuel_plan


def station(
    station_id,
    *,
    name="Station",
    address="I-35",
    city="Austin",
    state="TX",
    lat=Decimal("30.000000"),
    lng=Decimal("-97.000000"),
    price_per_gallon=Decimal("3.0000"),
    route_mile=0,
):
    return OptimizerStation(
        station_id=station_id,
        name=name,
        address=address,
        city=city,
        state=state,
        lat=lat,
        lng=lng,
        price_per_gallon=price_per_gallon,
        route_mile=route_mile,
    )


def test_optimizer_handles_trip_under_range_with_origin_station():
    origin = station(1, route_mile=0, price_per_gallon=Decimal("3.0000"))

    plan = build_fuel_plan(
        [origin],
        route_distance_miles=100,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
    )

    assert plan.total_gallons == Decimal("10.00")
    assert plan.total_cost == Decimal("30.00")
    assert plan.stops[0].gallons == Decimal("10.00")


def test_optimizer_buys_less_when_cheaper_station_is_reachable():
    expensive = station(1, price_per_gallon=Decimal("5.0000"), route_mile=0)
    cheap = station(2, name="Cheap", price_per_gallon=Decimal("3.0000"), route_mile=100)

    plan = build_fuel_plan(
        [expensive, cheap],
        route_distance_miles=300,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
    )

    assert plan.stops[0].gallons == Decimal("10.00")
    assert plan.stops[1].gallons == Decimal("20.00")
    assert plan.total_cost == Decimal("110.00")


def test_optimizer_raises_when_gap_exceeds_range():
    only = station(1, route_mile=0)

    with pytest.raises(NoFeasibleFuelPlanError):
        build_fuel_plan(
            [only],
            route_distance_miles=700,
            max_range_miles=500,
            miles_per_gallon=Decimal("10"),
        )


def test_optimizer_raises_when_no_stations_are_available():
    with pytest.raises(NoFeasibleFuelPlanError):
        build_fuel_plan(
            [],
            route_distance_miles=100,
            max_range_miles=500,
            miles_per_gallon=Decimal("10"),
        )


def test_optimizer_raises_when_first_station_is_beyond_range():
    first = station(1, route_mile=501)

    with pytest.raises(NoFeasibleFuelPlanError):
        build_fuel_plan(
            [first],
            route_distance_miles=600,
            max_range_miles=500,
            miles_per_gallon=Decimal("10"),
        )


def test_optimizer_warns_when_first_station_is_not_near_origin():
    first = station(1, route_mile=10)

    plan = build_fuel_plan(
        [first],
        route_distance_miles=100,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
    )

    assert any("starting fuel" in warning for warning in plan.warnings)


def test_optimizer_uses_cheapest_reachable_when_no_cheaper_station_is_ahead():
    current = station(1, price_per_gallon=Decimal("4.0000"), route_mile=100)
    close = station(2, name="Close", price_per_gallon=Decimal("4.5000"), route_mile=180)
    cheapest = station(3, name="Cheapest", price_per_gallon=Decimal("4.2000"), route_mile=300)

    plan = build_fuel_plan(
        [current, close, cheapest],
        route_distance_miles=800,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
    )

    assert plan.stops[0].station_id == current.station_id
    assert plan.stops[0].gallons == Decimal("20.00")
    assert plan.stops[1].station_id == cheapest.station_id


def test_optimizer_rounds_money_half_up():
    station_with_half_cent_price = station(
        1,
        price_per_gallon=Decimal("1.005"),
        route_mile=0,
    )

    plan = build_fuel_plan(
        [station_with_half_cent_price],
        route_distance_miles=10,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
    )

    assert plan.total_gallons == Decimal("1.00")
    assert plan.stops[0].cost == Decimal("1.01")
    assert plan.total_cost == Decimal("1.01")
