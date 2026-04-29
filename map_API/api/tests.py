import csv
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import polyline
import requests
from django.core.management import CommandError, call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import FuelStation
from .serializers import RouteRequestSerializer


class RouteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.payload = {'start_lat': 34, 'start_lng': -118, 'end_lat': 35, 'end_lng': -117}
        FuelStation.objects.create(station_name='Synthetic', city='Demo', state='CA', zip_code='00123',
                                   latitude=34, longitude=-118, fuel_type='Regular', price_per_gallon=4)

    def provider(self, distance=16093.44):
        response = Mock()
        response.json.return_value = {'routes': [{'summary': {'distance': distance},
                                                  'geometry': polyline.encode([(34, -118), (35, -117)])}]}
        return response

    def test_numeric_bounds(self):
        for key, value in [('start_lat', 91), ('end_lng', -181), ('vehicle_mpg', 0),
                           ('vehicle_mpg', float('inf')), ('tank_range_miles', 50)]:
            candidate = {**self.payload, key: value}
            self.assertFalse(RouteRequestSerializer(data=candidate).is_valid())

    @patch('api.views.requests.post')
    def test_valid_short_route(self, post):
        post.return_value = self.provider()
        result = self.client.post('/api/route/', self.payload, format='json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['total_distance_miles'], 10)
        self.assertEqual(result.data['total_fuel_cost'], 4)
        self.assertEqual(result.data['fuel_stops'], [])
        self.assertFalse(post.call_args.kwargs['allow_redirects'])

    @patch('api.views.requests.post')
    def test_missing_station_data_does_not_invent_zero_cost(self, post):
        FuelStation.objects.all().delete()
        self.assertEqual(self.client.post('/api/route/', self.payload, format='json').status_code, 503)
        post.assert_not_called()

    @patch('api.views.requests.post')
    def test_malformed_provider_and_sparse_unreachable_segment(self, post):
        post.return_value = self.provider()
        post.return_value.json.return_value = {'routes': [{}]}
        self.assertEqual(self.client.post('/api/route/', self.payload, format='json').status_code, 502)
        post.return_value = self.provider(1609344)
        self.assertEqual(self.client.post('/api/route/', self.payload, format='json').status_code, 422)

    @patch('api.views.requests.post')
    def test_provider_error_is_generic(self, post):
        post.side_effect = requests.RequestException('private upstream detail')
        result = self.client.post('/api/route/', self.payload, format='json')
        self.assertEqual(result.status_code, 502)
        self.assertNotIn('private', json.dumps(result.data))

    def test_csv_updates_price_and_preserves_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / 'stations.csv'
            header = ['station_name', 'city', 'state', 'zip_code', 'latitude', 'longitude', 'fuel_type',
                      'price_per_gallon']

            def write(price):
                with filename.open('w', newline='') as target:
                    writer = csv.writer(target)
                    writer.writerow(header)
                    writer.writerow(['Synthetic', 'Demo', 'CA', '00123', 34, -118, 'Regular', price])
            write(4.2)
            call_command('load_fuel_data', path=str(filename), stdout=io.StringIO())
            write(4.5)
            call_command('load_fuel_data', path=str(filename), stdout=io.StringIO())
        self.assertEqual(FuelStation.objects.count(), 1)
        station = FuelStation.objects.get()
        self.assertEqual(station.zip_code, '00123')
        self.assertEqual(station.price_per_gallon, 4.5)

    def test_csv_with_a_bad_row_imports_nothing(self):
        FuelStation.objects.all().delete()
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / 'stations.csv'
            filename.write_text(
                'station_name,city,state,zip_code,latitude,longitude,fuel_type,price_per_gallon\n'
                'Good,Demo,CA,00123,34,-118,Regular,4.10\n'
                'Free fuel,Demo,CA,00124,34.1,-118.1,Regular,0\n')
            with self.assertRaises(CommandError):
                call_command('load_fuel_data', path=str(filename), stdout=io.StringIO())
        self.assertFalse(FuelStation.objects.exists())

    def test_bundled_sample_loads(self):
        FuelStation.objects.all().delete()
        call_command('load_fuel_data', stdout=io.StringIO())
        self.assertEqual(FuelStation.objects.count(), 50)
        self.assertFalse(FuelStation.objects.filter(price_per_gallon__lte=0).exists())


class FuelCostRuleTests(TestCase):
    """Routes along the -100 meridian, one point per degree of latitude (about 69 miles)."""

    def setUp(self):
        self.client = APIClient()
        self.points = [(30 + step, -100.0) for step in range(4)]

    def post_route(self, post, distance_meters, tank_range):
        response = Mock()
        response.json.return_value = {'routes': [{'summary': {'distance': distance_meters},
                                                  'geometry': polyline.encode(self.points)}]}
        post.return_value = response
        payload = {'start_lat': 30, 'start_lng': -100, 'end_lat': 33, 'end_lng': -100,
                   'vehicle_mpg': 20, 'tank_range_miles': tank_range}
        return self.client.post('/api/route/', payload, format='json')

    @patch('api.views.requests.post')
    def test_fallback_price_ignores_zero_priced_rows(self, post):
        FuelStation.objects.create(station_name='Bad row', city='X', state='TX', zip_code='1',
                                   latitude=10, longitude=10, fuel_type='Regular', price_per_gallon=0)
        FuelStation.objects.create(station_name='Real', city='Y', state='TX', zip_code='2',
                                   latitude=10, longitude=11, fuel_type='Regular', price_per_gallon=4)
        result = self.post_route(post, 200 / 0.000621371, tank_range=500)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['total_fuel_cost'], 40)

    @patch('api.views.requests.post')
    def test_no_stop_when_destination_is_within_remaining_range(self, post):
        FuelStation.objects.create(station_name='Last town', city='Z', state='TX', zip_code='3',
                                   latitude=32, longitude=-100, fuel_type='Regular', price_per_gallon=3)
        # 210 miles on a 220-mile tank: range dips under the 50-mile buffer, but the trip still finishes.
        result = self.post_route(post, 210 / 0.000621371, tank_range=220)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['fuel_stops'], [])
        self.assertEqual(result.data['total_fuel_cost'], 31.5)

    @patch('api.views.requests.post')
    def test_station_lookup_is_one_query_however_many_stops(self, post):
        self.points = [(30 + step, -100.0) for step in range(9)]
        for step in range(9):
            FuelStation.objects.create(station_name=f'Stop {step}', city='T', state='TX', zip_code=str(step),
                                       latitude=30 + step, longitude=-100.02, fuel_type='Regular',
                                       price_per_gallon=3 + step / 10)
        with self.assertNumQueries(2):
            result = self.post_route(post, 552 / 0.000621371, tank_range=150)
        self.assertEqual(result.status_code, 200)
        self.assertEqual([s['station_name'] for s in result.data['fuel_stops']], ['Stop 2', 'Stop 4', 'Stop 6'])


class ProviderAndLimitTests(TestCase):
    payload = {'start_lat': 34, 'start_lng': -118, 'end_lat': 35, 'end_lng': -117}

    def setUp(self):
        self.client = APIClient()
        FuelStation.objects.create(station_name='Synthetic', city='Demo', state='CA', zip_code='00123',
                                   latitude=34, longitude=-118, fuel_type='Regular', price_per_gallon=4)

    @patch('api.views.requests.post')
    def test_timeout_maps_to_504_and_uses_configured_endpoint(self, post):
        post.side_effect = requests.Timeout()
        with self.settings(ORS_URL='http://ors.local/route', ORS_TIMEOUT_SECONDS=3):
            result = self.client.post('/api/route/', self.payload, format='json')
        self.assertEqual(result.status_code, 504)
        self.assertEqual(post.call_args.args[0], 'http://ors.local/route')
        self.assertEqual(post.call_args.kwargs['timeout'], 3)

    @patch('api.views.requests.post')
    def test_missing_key_is_503_without_calling_provider(self, post):
        with self.settings(ORS_API_KEY=''):
            result = self.client.post('/api/route/', self.payload, format='json')
        self.assertEqual(result.status_code, 503)
        post.assert_not_called()

    def test_identical_endpoints_rejected(self):
        same = {**self.payload, 'end_lat': 34, 'end_lng': -118}
        self.assertEqual(self.client.post('/api/route/', same, format='json').status_code, 400)

    @patch('api.views.requests.post')
    def test_route_requests_are_rate_limited(self, post):
        from django.core.cache import cache
        from rest_framework.throttling import ScopedRateThrottle
        cache.clear()
        post.side_effect = requests.Timeout()
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'route': '2/minute'}):
            codes = [self.client.post('/api/route/', self.payload, format='json').status_code for _ in range(3)]
        cache.clear()
        self.assertEqual(codes, [504, 504, 429])
