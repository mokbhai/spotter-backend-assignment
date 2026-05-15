from dataclasses import dataclass
from math import asin, cos, hypot, isfinite, pi, radians, sin
from numbers import Real


EARTH_RADIUS_MILES = 3958.7613


@dataclass(frozen=True)
class ProjectedPoint:
    distance_to_route_miles: float
    route_mile: float


def haversine_miles(lat1, lng1, lat2, lng2):
    lat1_rad = radians(float(lat1))
    lng1_rad = radians(float(lng1))
    lat2_rad = radians(float(lat2))
    lng2_rad = radians(float(lng2))

    delta_lat = lat2_rad - lat1_rad
    delta_lng = lng2_rad - lng1_rad

    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * asin(min(1, haversine**0.5))


def route_points(geometry):
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if (
        not isinstance(geometry, dict)
        or geometry.get("type") != "LineString"
        or not isinstance(coordinates, list)
        or len(coordinates) < 2
    ):
        raise ValueError("Route geometry must be a LineString with at least two coordinates.")

    points = []
    for coordinate in coordinates:
        if not _is_valid_position(coordinate):
            raise ValueError("Route geometry contains invalid coordinates.")
        lng, lat = coordinate[:2]
        points.append((float(lat), float(lng)))

    return points


def expanded_bounding_box(points, miles):
    if not points:
        raise ValueError("At least one point is required.")
    miles = _validate_corridor_miles(miles)

    latitudes = [point[0] for point in points]
    longitudes = [point[1] for point in points]
    min_lat = min(latitudes)
    max_lat = max(latitudes)
    min_lng = min(longitudes)
    max_lng = max(longitudes)

    lat_delta = _degrees_for_miles(miles)
    mean_lat = radians((min_lat + max_lat) / 2)
    lng_scale = max(cos(mean_lat), 0.01)
    lng_delta = lat_delta / lng_scale

    return (
        min_lat - lat_delta,
        max_lat + lat_delta,
        min_lng - lng_delta,
        max_lng + lng_delta,
    )


def cumulative_route_miles(points):
    if len(points) < 2:
        raise ValueError("At least two route points are required.")

    totals = [0.0]
    for start, end in zip(points, points[1:]):
        totals.append(
            totals[-1] + haversine_miles(start[0], start[1], end[0], end[1])
        )
    return totals


def downsample_route_points(points, route_miles, spacing_miles):
    if len(points) < 2:
        raise ValueError("At least two route points are required.")
    if len(route_miles) != len(points):
        raise ValueError("Route mileage count must match route point count.")

    spacing_miles = _validate_positive_spacing_miles(spacing_miles)
    sampled_points = [points[0]]
    sampled_miles = [route_miles[0]]
    last_kept_mile = route_miles[0]

    for point, route_mile in zip(points[1:-1], route_miles[1:-1]):
        if route_mile - last_kept_mile >= spacing_miles:
            sampled_points.append(point)
            sampled_miles.append(route_mile)
            last_kept_mile = route_mile

    if sampled_points[-1] != points[-1]:
        sampled_points.append(points[-1])
        sampled_miles.append(route_miles[-1])

    return sampled_points, sampled_miles


def downsample_linestring_geometry(geometry, spacing_miles):
    points = route_points(geometry)
    route_miles = cumulative_route_miles(points)
    sampled_points, _ = downsample_route_points(points, route_miles, spacing_miles)
    return {
        "type": "LineString",
        "coordinates": [[lng, lat] for lat, lng in sampled_points],
    }


def project_point_to_route(lat, lng, points, route_miles=None):
    if len(points) < 2:
        raise ValueError("At least two route points are required.")

    if route_miles is None:
        route_miles = cumulative_route_miles(points)
    elif len(route_miles) != len(points):
        raise ValueError("Route mileage count must match route point count.")

    best_projection = None

    for index, (start, end) in enumerate(zip(points, points[1:])):
        projected = _project_point_to_segment(
            float(lat),
            float(lng),
            start,
            end,
            route_miles[index],
            route_miles[index + 1] - route_miles[index],
        )
        if (
            best_projection is None
            or projected.distance_to_route_miles
            < best_projection.distance_to_route_miles
        ):
            best_projection = projected

    return best_projection


def _project_point_to_segment(lat, lng, start, end, start_route_mile, segment_route_miles):
    mean_lat = radians((start[0] + end[0] + float(lat)) / 3)
    miles_per_radian_lng = EARTH_RADIUS_MILES * cos(mean_lat)

    segment_x = radians(end[1] - start[1]) * miles_per_radian_lng
    segment_y = radians(end[0] - start[0]) * EARTH_RADIUS_MILES
    point_x = radians(float(lng) - start[1]) * miles_per_radian_lng
    point_y = radians(float(lat) - start[0]) * EARTH_RADIUS_MILES

    segment_length_squared = segment_x**2 + segment_y**2
    if segment_length_squared == 0:
        distance = hypot(point_x, point_y)
        return ProjectedPoint(distance, start_route_mile)

    t = ((point_x * segment_x) + (point_y * segment_y)) / segment_length_squared
    clamped_t = min(1.0, max(0.0, t))
    closest_x = clamped_t * segment_x
    closest_y = clamped_t * segment_y
    distance = hypot(point_x - closest_x, point_y - closest_y)
    return ProjectedPoint(
        distance_to_route_miles=distance,
        route_mile=start_route_mile + (clamped_t * segment_route_miles),
    )


def _degrees_for_miles(miles):
    return (float(miles) / EARTH_RADIUS_MILES) * (180 / pi)


def _is_coordinate_number(value):
    return isinstance(value, Real) and not isinstance(value, bool)


def _is_valid_position(coordinate):
    if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
        return False

    lng, lat = coordinate[:2]
    if not _is_coordinate_number(lng) or not _is_coordinate_number(lat):
        return False

    lng = float(lng)
    lat = float(lat)
    return isfinite(lng) and isfinite(lat) and -180 <= lng <= 180 and -90 <= lat <= 90


def _validate_corridor_miles(miles):
    if not _is_coordinate_number(miles):
        raise ValueError("Corridor miles must be a finite non-negative number.")

    miles = float(miles)
    if not isfinite(miles) or miles < 0:
        raise ValueError("Corridor miles must be a finite non-negative number.")

    return miles


def _validate_positive_spacing_miles(miles):
    miles = _validate_corridor_miles(miles)
    if miles <= 0:
        raise ValueError("Spacing miles must be positive.")
    return miles
