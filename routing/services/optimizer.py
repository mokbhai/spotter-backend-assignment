from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from routing.exceptions import NoFeasibleFuelPlanError


@dataclass(frozen=True)
class OptimizerStation:
    station_id: int
    name: str
    address: str
    city: str
    state: str
    lat: Decimal
    lng: Decimal
    price_per_gallon: Decimal
    route_mile: float


@dataclass(frozen=True)
class FuelStop:
    station_id: int
    name: str
    address: str
    city: str
    state: str
    lat: Decimal
    lng: Decimal
    price_per_gallon: Decimal
    route_mile: float
    gallons: Decimal
    cost: Decimal


@dataclass(frozen=True)
class FuelPlan:
    total_gallons: Decimal
    total_cost: Decimal
    stops: list[FuelStop]
    warnings: list[str]


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def gallons(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _decimal(value: float | int | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _build_stop(station: OptimizerStation, gallons_purchased: Decimal, cost: Decimal) -> FuelStop:
    return FuelStop(
        station_id=station.station_id,
        name=station.name,
        address=station.address,
        city=station.city,
        state=station.state,
        lat=station.lat,
        lng=station.lng,
        price_per_gallon=station.price_per_gallon,
        route_mile=station.route_mile,
        gallons=gallons_purchased,
        cost=cost,
    )


def build_fuel_plan(
    stations: list[OptimizerStation],
    route_distance_miles: float,
    max_range_miles: float,
    miles_per_gallon: Decimal,
) -> FuelPlan:
    ordered = sorted(stations, key=lambda station: station.route_mile)
    if not ordered:
        raise NoFeasibleFuelPlanError("No fuel stations are available near this route.")

    if ordered[0].route_mile > max_range_miles:
        raise NoFeasibleFuelPlanError("No reachable first fuel station is available.")

    warnings: list[str] = []
    if ordered[0].route_mile > 5:
        warnings.append("Plan assumes enough starting fuel to reach the first selected station.")

    stops: list[FuelStop] = []
    route_distance = _decimal(route_distance_miles)
    max_range = _decimal(max_range_miles)
    mpg = _decimal(miles_per_gallon)

    current_index = 0
    accounted_mile = Decimal("0")
    current_station_mile = _decimal(ordered[current_index].route_mile)

    while accounted_mile < route_distance:
        current_station = ordered[current_index]
        current_price = current_station.price_per_gallon

        reachable: list[tuple[int, OptimizerStation]] = []
        for index in range(current_index + 1, len(ordered)):
            station = ordered[index]
            station_mile = _decimal(station.route_mile)
            if station_mile - current_station_mile <= max_range:
                reachable.append((index, station))

        selected_index: int | None = None
        target_mile = route_distance

        cheaper = next(
            (
                (index, station)
                for index, station in reachable
                if station.price_per_gallon < current_price
            ),
            None,
        )
        if cheaper is not None:
            selected_index, selected_station = cheaper
            target_mile = _decimal(selected_station.route_mile)
        elif route_distance - current_station_mile <= max_range:
            selected_index = None
        elif not reachable:
            raise NoFeasibleFuelPlanError("No reachable downstream fuel station is available.")
        else:
            selected_index, selected_station = min(
                reachable,
                key=lambda item: (
                    item[1].price_per_gallon,
                    _decimal(item[1].route_mile),
                    item[1].station_id,
                ),
            )
            target_mile = _decimal(selected_station.route_mile)

        miles_to_cover = target_mile - accounted_mile
        stop_gallons = gallons(miles_to_cover / mpg)
        stop_cost = money(stop_gallons * current_price)

        if stop_gallons > 0:
            stops.append(_build_stop(current_station, stop_gallons, stop_cost))

        accounted_mile = target_mile

        if selected_index is None:
            break

        current_index = selected_index
        current_station_mile = _decimal(ordered[current_index].route_mile)

    total_gallons = gallons(sum((stop.gallons for stop in stops), Decimal("0")))
    total_cost = money(sum((stop.cost for stop in stops), Decimal("0")))

    return FuelPlan(
        total_gallons=total_gallons,
        total_cost=total_cost,
        stops=stops,
        warnings=warnings,
    )
