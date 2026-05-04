import requests
import polyline
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import RouteRequestSerializer
from .models import FuelStation
from math import radians, cos, sin, asin, sqrt


def haversine(lat1, lon1, lat2, lon2):
    """Distance in miles between two points"""

    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    angle = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    central_angle = 2 * asin(sqrt(angle))
    return 3956 * central_angle

def stations_near_point(lat, lng, radius_miles=50):
    """Return fuel stations within radius"""
    
    lat_deg = radius_miles / 69.17
    lng_deg = radius_miles / (69.17 * cos(radians(lat)))

    nearby_stations = FuelStation.objects.filter(
        latitude__range=(lat - lat_deg, lat + lat_deg),
        longitude__range=(lng - lng_deg, lng + lng_deg)
    )

    # Precise haversine check
    return [s for s in nearby_stations if haversine(lat, lng, s.latitude, s.longitude) <= radius_miles]

class RouteAPIView(APIView):
    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        start = [data['start_lng'], data['start_lat']]
        end = [data['end_lng'], data['end_lat']]

        route_url = settings.ORS_URL
        try:
            resp = requests.post(
                route_url,
                headers={'Authorization': settings.ORS_API_KEY, 'Content-Type': 'application/json'},
                json={"coordinates": [start, end]},
                timeout=10
            )
            resp.raise_for_status()
            route_resp = resp.json()
        except requests.exceptions.Timeout:
            return Response({"error": "Routing service timed out."}, status=504)
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Routing service error: {str(e)}"}, status=502)

        if "routes" not in route_resp or not route_resp["routes"]:
            return Response({"error": "No route found."}, status=400)

        route_data = route_resp["routes"][0]
        actual_distance_meters = route_data["summary"]["distance"]
        total_distance_miles = actual_distance_meters * 0.000621371
        route_coords = polyline.decode(route_data["geometry"])

        tank_range = data['tank_range_miles']
        mpg = data['vehicle_mpg']
        SAFETY_BUFFER = 50  # miles before empty
        SEARCH_RADIUS = 50  # search radius for fuel stations

        # for distance accuracy we will track distance relative to the API's total
        fuel_stops = []
        total_fuel_cost = 0
        remaining_range = tank_range

        # We need to know how far we have traveled along the polyline segments
        # and normalize it to match the total_distance_miles from the API.
        polyline_segments = []
        polyline_total_haversine = 0
        for i in range(len(route_coords) - 1):
            p1, p2 = route_coords[i], route_coords[i+1]
            distance = haversine(p1[0], p1[1], p2[0], p2[1])
            polyline_segments.append(distance)
            polyline_total_haversine += distance

        # API total might differ slightly from haversine sum of polyline points
        norm_factor = total_distance_miles / polyline_total_haversine if polyline_total_haversine > 0 else 1

        distance_since_refuel = 0

        for i, segment_distance in enumerate(polyline_segments):
            normalized_segment_distance = segment_distance * norm_factor
            distance_since_refuel += normalized_segment_distance
            remaining_range -= normalized_segment_distance

            if remaining_range < SAFETY_BUFFER:
                current_point = route_coords[i+1]
                nearby = stations_near_point(current_point[0], current_point[1], radius_miles=SEARCH_RADIUS)

                # If no stations within search radius expand search slightly
                if not nearby:
                    nearby = stations_near_point(current_point[0], current_point[1], radius_miles=100)

                if nearby:
                    min_station = min(nearby, key=lambda x: x.price_per_gallon)

                    fuel_needed = distance_since_refuel / mpg
                    total_fuel_cost += fuel_needed * min_station.price_per_gallon

                    fuel_stops.append({
                        "station_name": min_station.station_name,
                        "latitude": min_station.latitude,
                        "longitude": min_station.longitude,
                        "price_per_gallon": min_station.price_per_gallon,
                    })

                    # Reset range
                    remaining_range = tank_range
                    distance_since_refuel = 0

        # Total fuel cost should cover the whole trip 
        # If we didn't refuel at the very end we should still account for the fuel used for the last segemnt
        if distance_since_refuel > 0:
            # We either need to refuel to finish or we use what is in the tank
            # If we don't refuel at the end, we assume we consumed the remaining distance worth of fuel
            # but we don't have a station price for it. We will use the price of the last stop or minimum from the DB.
            if fuel_stops:
                last_price = fuel_stops[-1]["price_per_gallon"]
            else:
                all_stations = FuelStation.objects.all()
                last_price = min(all_stations, key=lambda x: x.price_per_gallon).price_per_gallon if all_stations.exists() else 0

            total_fuel_cost += (distance_since_refuel / mpg) * last_price

        return Response({
            "route": route_coords,
            "fuel_stops": fuel_stops,
            "total_distance_miles": round(total_distance_miles, 2),
            "total_fuel_cost": round(total_fuel_cost, 2),
        })
