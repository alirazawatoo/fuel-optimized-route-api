import csv
import math
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from api.models import FuelStation

class Command(BaseCommand):
    help = 'Load station prices from a CSV; existing station identities have their price updated'
    def add_arguments(self, parser):
        parser.add_argument('--path', default=str(Path(settings.BASE_DIR) / 'fuel_prices_sample.csv'))
    def handle(self, *args, **options):
        rows = []
        try:
            with open(options['path'], newline='', encoding='utf-8-sig') as source:
                for number, row in enumerate(csv.DictReader(source), 2):
                    if not any(row.values()):
                        continue
                    identity = {key: row[key].strip() for key in ['station_name', 'city', 'state', 'zip_code', 'fuel_type']}
                    if any(not value for value in identity.values()):
                        raise ValueError(f'Missing identity on line {number}')
                    lat, lng, price = (float(row[key]) for key in ['latitude', 'longitude', 'price_per_gallon'])
                    if not all(math.isfinite(value) for value in [lat, lng, price]) or not -90 <= lat <= 90 or not -180 <= lng <= 180 or price <= 0:
                        raise ValueError(f'Invalid coordinate or price on line {number}')
                    identity.update(latitude=lat, longitude=lng)
                    rows.append((identity, price))
        except (OSError, KeyError, TypeError, ValueError):
            raise CommandError('CSV is unreadable or contains invalid station fields')
        with transaction.atomic():
            for identity, price in rows:
                FuelStation.objects.update_or_create(**identity, defaults={'price_per_gallon': price})
        self.stdout.write(self.style.SUCCESS(f'Loaded {len(rows)} station rows'))
