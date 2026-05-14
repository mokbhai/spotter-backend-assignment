from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from routing.services.candidates import find_candidate_stations
from routing.services.geocoding import resolve_location
from routing.services.optimizer import OptimizerStation, build_fuel_plan
from routing.services.osrm import OSRMClient, Route


class Router(Protocol):
    def route(self, start_lat, start_lng, dest_lat, dest_lng) -> Route:
        ...


def resolve_input_location(value):
    if isinstance(value, Mapping):
        return value["lat"], value["lng"]

    if isinstance(value, str):
        location = resolve_location(value)
        return location.latitude, location.longitude

    raise TypeError("Location must be a coordinate mapping or address string.")


def build_route_fuel_plan(
    *,
    start,
    destination,
    corridor_miles,
    max_range_miles,
    miles_per_gallon,
    router: Router | None = None,
):
    start_lat, start_lng = resolve_input_location(start)
    dest_lat, dest_lng = resolve_input_location(destination)

    route = (router or OSRMClient()).route(start_lat, start_lng, dest_lat, dest_lng)
    candidates = find_candidate_stations(route.geometry, corridor_miles)
    stations = [
        OptimizerStation(
            station_id=candidate.station.id,
            name=candidate.station.name,
            address=candidate.station.address,
            city=candidate.station.city,
            state=candidate.station.state,
            lat=candidate.station.latitude,
            lng=candidate.station.longitude,
            price_per_gallon=candidate.station.retail_price,
            route_mile=candidate.route_mile,
        )
        for candidate in candidates
    ]
    fuel_plan = build_fuel_plan(
        stations,
        route_distance_miles=route.distance_miles,
        max_range_miles=max_range_miles,
        miles_per_gallon=miles_per_gallon,
    )

    return {
        "route": {
            "distance_miles": round(route.distance_miles, 2),
            "geometry": route.geometry,
        },
        "fuel_plan": {
            "max_range_miles": max_range_miles,
            "miles_per_gallon": miles_per_gallon,
            "total_gallons": fuel_plan.total_gallons,
            "total_cost": fuel_plan.total_cost,
            "currency": "USD",
            "starting_fuel_assumption": serialize_starting_fuel_assumption(
                fuel_plan.starting_fuel_assumption
            ),
            "stops": [
                {
                    "station_id": stop.station_id,
                    "name": stop.name,
                    "address": stop.address,
                    "city": stop.city,
                    "state": stop.state,
                    "lat": stop.lat,
                    "lng": stop.lng,
                    "price_per_gallon": stop.price_per_gallon,
                    "route_mile": round(stop.route_mile, 2),
                    "gallons": stop.gallons,
                    "cost": stop.cost,
                }
                for stop in fuel_plan.stops
            ],
        },
        "warnings": fuel_plan.warnings,
        "metadata": {"routing_provider": "osrm"},
    }


def serialize_starting_fuel_assumption(assumption):
    if assumption is None:
        return None

    return {
        "distance_miles": round(assumption.distance_miles, 2),
        "gallons": assumption.gallons,
        "cost": assumption.cost,
        "price_per_gallon": assumption.price_per_gallon,
        "priced_at_station_id": assumption.priced_at_station_id,
    }
