"""Fuel-stop heuristic, kept free of HTTP and ORM code so it can be tested directly."""
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MILES = 3956
MILES_PER_DEGREE_LAT = 69.17
SAFETY_BUFFER_MILES = 50
SEARCH_RADIUS_MILES = 50
WIDE_SEARCH_RADIUS_MILES = 100


class UnreachableRoute(Exception):
    """A single sampled segment is longer than the fuel left in the tank."""


@dataclass(frozen=True)
class Station:
    name: str
    latitude: float
    longitude: float
    price_per_gallon: float


@dataclass
class FuelPlan:
    stops: list
    total_fuel_cost: float


def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles."""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    angle = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    # Rounding can push the angle a hair outside [0, 1], which asin rejects.
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(max(0, min(1, angle))))


def route_bounds(route_coords, margin_miles=WIDE_SEARCH_RADIUS_MILES):
    """Lat/lng box around the route, widened by the largest search radius.

    The longitude range is None when the box would wrap the antimeridian or a
    pole; callers then filter by latitude only and let haversine do the rest.
    """
    lats = [lat for lat, _ in route_coords]
    lngs = [lng for _, lng in route_coords]
    lat_margin = margin_miles / MILES_PER_DEGREE_LAT
    min_lat, max_lat = min(lats) - lat_margin, max(lats) + lat_margin
    if min_lat <= -90 or max_lat >= 90:
        return (max(min_lat, -90), min(max_lat, 90)), None
    widest_lat = max(abs(min_lat), abs(max_lat))
    lng_margin = margin_miles / (MILES_PER_DEGREE_LAT * cos(radians(widest_lat)))
    min_lng, max_lng = min(lngs) - lng_margin, max(lngs) + lng_margin
    if min_lng < -180 or max_lng > 180 or max(lngs) - min(lngs) > 180:
        return (min_lat, max_lat), None
    return (min_lat, max_lat), (min_lng, max_lng)


def cheapest_nearby(stations, lat, lng):
    for radius in (SEARCH_RADIUS_MILES, WIDE_SEARCH_RADIUS_MILES):
        nearby = [s for s in stations if haversine(lat, lng, s.latitude, s.longitude) <= radius]
        if nearby:
            return min(nearby, key=lambda s: s.price_per_gallon)
    return None


def plan_fuel_stops(route_coords, total_distance_miles, tank_range, mpg, stations, fallback_price):
    """Walk the route and refuel at the cheapest nearby station when range runs low.

    Segment lengths are straight-line distances between polyline points,
    scaled so they add up to the provider's driving distance. The tank starts
    full; fuel burned after the last stop (or on a stop-free trip) is priced at
    the last stop, or at ``fallback_price`` when there was no stop.
    """
    segments = [haversine(*a, *b) for a, b in zip(route_coords, route_coords[1:])]
    sampled_total = sum(segments)
    scale = total_distance_miles / sampled_total if sampled_total > 0 else 1

    stops = []
    cost = 0.0
    remaining_range = tank_range
    since_refuel = 0.0
    travelled = 0.0
    for point, segment in zip(route_coords[1:], segments):
        segment *= scale
        if segment > remaining_range:
            raise UnreachableRoute
        since_refuel += segment
        travelled += segment
        remaining_range -= segment
        if remaining_range >= SAFETY_BUFFER_MILES or total_distance_miles - travelled <= remaining_range:
            continue
        station = cheapest_nearby(stations, *point)
        if station is None:
            continue
        cost += since_refuel / mpg * station.price_per_gallon
        stops.append({
            "station_name": station.name,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "price_per_gallon": station.price_per_gallon,
        })
        remaining_range = tank_range
        since_refuel = 0.0

    if since_refuel > 0:
        price = stops[-1]["price_per_gallon"] if stops else fallback_price
        cost += since_refuel / mpg * price
    return FuelPlan(stops=stops, total_fuel_cost=cost)
