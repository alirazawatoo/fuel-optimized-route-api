import csv
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
import polyline
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
        import requests
        post.side_effect = requests.RequestException('private upstream detail')
        result = self.client.post('/api/route/', self.payload, format='json')
        self.assertEqual(result.status_code, 502)
        self.assertNotIn('private', json.dumps(result.data))
    def test_csv_updates_price_and_preserves_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / 'stations.csv'
            header = ['station_name','city','state','zip_code','latitude','longitude','fuel_type','price_per_gallon']
            def write(price):
                with filename.open('w', newline='') as target:
                    writer = csv.writer(target)
                    writer.writerow(header)
                    writer.writerow(['Synthetic','Demo','CA','00123',34,-118,'Regular',price])
            write(4.2)
            call_command('load_fuel_data', path=str(filename), stdout=io.StringIO())
            write(4.5)
            call_command('load_fuel_data', path=str(filename), stdout=io.StringIO())
        self.assertEqual(FuelStation.objects.count(), 1)
        station = FuelStation.objects.get()
        self.assertEqual(station.zip_code, '00123')
        self.assertEqual(station.price_per_gallon, 4.5)
