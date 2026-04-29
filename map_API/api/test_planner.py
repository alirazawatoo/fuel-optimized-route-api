from django.test import SimpleTestCase

from api.planner import Station, UnreachableRoute, haversine, plan_fuel_stops, route_bounds

# Points one degree of latitude apart on the -100 meridian: about 69 miles each.
MERIDIAN = [(30 + step, -100.0) for step in range(9)]


def leg_miles(points):
    return sum(haversine(*a, *b) for a, b in zip(points, points[1:]))


class PlannerTests(SimpleTestCase):
    def test_haversine_known_distance_and_rounding_clamp(self):
        self.assertAlmostEqual(haversine(34.0522, -118.2437, 40.7128, -74.006), 2445, delta=5)
        self.assertEqual(haversine(10, 20, 10, 20), 0)
        self.assertAlmostEqual(haversine(0, 0, 0, 180), 3956 * 3.141592653589793, places=3)

    def test_refuels_at_cheapest_station_near_the_low_point(self):
        stations = [Station('Pricey', 33.0, -100.0, 5.0), Station('Cheap', 33.1, -100.2, 3.0),
                    Station('Cheap north', 36.0, -100.1, 3.0), Station('Far away', 45.0, -80.0, 1.0)]
        distance = leg_miles(MERIDIAN)
        plan = plan_fuel_stops(MERIDIAN, distance, tank_range=250, mpg=25, stations=stations, fallback_price=9)
        self.assertEqual([s['station_name'] for s in plan.stops], ['Cheap', 'Cheap north'])
        self.assertAlmostEqual(plan.total_fuel_cost, distance / 25 * 3.0, places=6)

    def test_no_stop_when_destination_is_within_remaining_range(self):
        route = MERIDIAN[:4]  # about 207 miles
        stations = [Station('Near the end', 33.0, -100.0, 3.0)]
        plan = plan_fuel_stops(route, leg_miles(route), tank_range=220, mpg=20, stations=stations, fallback_price=4)
        self.assertEqual(plan.stops, [])
        self.assertAlmostEqual(plan.total_fuel_cost, leg_miles(route) / 20 * 4, places=6)

    def test_segment_longer_than_tank_is_unreachable(self):
        with self.assertRaises(UnreachableRoute):
            plan_fuel_stops([(30, -100), (35, -100)], 345, tank_range=300, mpg=20, stations=[], fallback_price=4)

    def test_keeps_driving_when_no_station_in_range_then_fails_if_tank_runs_dry(self):
        with self.assertRaises(UnreachableRoute):
            plan_fuel_stops(MERIDIAN, leg_miles(MERIDIAN), tank_range=150, mpg=20, stations=[], fallback_price=4)

    def test_station_across_the_antimeridian_is_found(self):
        route = [(51.0, 178.5), (51.0, 179.0), (51.0, 179.5), (51.0, -179.8), (51.0, -179.3), (51.0, -178.8)]
        (_, _), lng_range = route_bounds(route)
        self.assertIsNone(lng_range)
        stations = [Station('Dateline', 51.0, -179.9, 4.0)]
        plan = plan_fuel_stops(route, leg_miles(route), tank_range=70, mpg=30, stations=stations, fallback_price=9)
        self.assertEqual(plan.stops[0]['station_name'], 'Dateline')

    def test_route_bounds_cover_the_wide_search_radius(self):
        (min_lat, max_lat), (min_lng, max_lng) = route_bounds([(34, -118), (35, -117)])
        self.assertLess(haversine(34, -118, min_lat, -118), 101)
        self.assertGreater(haversine(34, -118, min_lat, -118), 99)
        self.assertGreater(haversine(35, -117, 35, max_lng), 99)
