import pandas as pd
from django.core.management.base import BaseCommand
from api.models import FuelStation

class Command(BaseCommand):
    help = "Load fuel prices from CSV"

    def handle(self, *args, **kwargs):
        df = pd.read_csv('fuel_prices_sample.csv')
        for _, row in df.iterrows():
            FuelStation.objects.update_or_create(
                station_name=row['station_name'],
                city=row['city'],
                state=row['state'],
                zip_code=row['zip_code'],
                latitude=row['latitude'],
                longitude=row['longitude'],
                fuel_type=row['fuel_type'],
                price_per_gallon=row['price_per_gallon']
            )
        self.stdout.write(self.style.SUCCESS("Fuel stations loaded successfully"))
