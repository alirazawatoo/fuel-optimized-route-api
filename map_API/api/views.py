from math import isfinite

import polyline
import requests
from django.conf import settings
from django.db.models import Min
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FuelStation
from .planner import Station, UnreachableRoute, plan_fuel_stops, route_bounds
from .serializers import RouteRequestSerializer

METERS_TO_MILES = 0.000621371
MAX_ROUTE_POINTS = 10000


def fetch_route(start, end):
    """Ask ORS for a driving route; returns (distance in miles, [(lat, lng), ...])."""
    response = requests.post(
        settings.ORS_URL,
        headers={'Authorization': settings.ORS_API_KEY, 'Content-Type': 'application/json'},
        json={"coordinates": [start, end]},
        timeout=10, allow_redirects=False,
    )
    response.raise_for_status()
    route = response.json()["routes"][0]
    meters = route["summary"]["distance"]
    if isinstance(meters, bool) or not isinstance(meters, (int, float)) or not isfinite(meters) or meters <= 0:
        raise ValueError("route distance")
    coords = polyline.decode(route["geometry"])
    if not 2 <= len(coords) <= MAX_ROUTE_POINTS:
        raise ValueError("route point count")
    for point in coords:
        if not (len(point) == 2 and all(isfinite(v) for v in point)
                and -90 <= point[0] <= 90 and -180 <= point[1] <= 180):
            raise ValueError("route point")
    return meters * METERS_TO_MILES, coords


def stations_along(route_coords):
    """Every priced station that could fall inside the widest search radius, in one query."""
    (min_lat, max_lat), lng_range = route_bounds(route_coords)
    stations = FuelStation.objects.filter(price_per_gallon__gt=0, latitude__range=(min_lat, max_lat))
    if lng_range:
        stations = stations.filter(longitude__range=lng_range)
    return [Station(s.station_name, s.latitude, s.longitude, s.price_per_gallon)
            for s in stations.only('station_name', 'latitude', 'longitude', 'price_per_gallon')]


class RouteAPIView(APIView):
    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not settings.ORS_API_KEY:
            return Response({"error": "Routing provider is not configured."}, status=503)
        cheapest_price = FuelStation.objects.filter(price_per_gallon__gt=0).aggregate(
            price=Min('price_per_gallon'))['price']
        if cheapest_price is None:
            return Response({"error": "Load positive station prices before requesting a route."}, status=503)

        # ORS expects [lng, lat] pairs.
        start = [data['start_lng'], data['start_lat']]
        end = [data['end_lng'], data['end_lat']]
        try:
            total_distance_miles, route_coords = fetch_route(start, end)
        except requests.exceptions.Timeout:
            return Response({"error": "Routing service timed out."}, status=504)
        except requests.exceptions.RequestException:
            return Response({"error": "Routing provider request failed."}, status=502)
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            return Response({"error": "Routing provider returned invalid route data."}, status=502)

        try:
            plan = plan_fuel_stops(route_coords, total_distance_miles, data['tank_range_miles'],
                                   data['vehicle_mpg'], stations_along(route_coords), cheapest_price)
        except UnreachableRoute:
            return Response(
                {"error": "This route sampling cannot establish reachable fuel stops within the tank range."},
                status=422)

        return Response({
            "route": route_coords,
            "fuel_stops": plan.stops,
            "total_distance_miles": round(total_distance_miles, 2),
            "total_fuel_cost": round(plan.total_fuel_cost, 2),
        })
