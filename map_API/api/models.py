from django.db import models


class FuelStation(models.Model):
    station_name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50)
    zip_code = models.CharField(max_length=20)
    latitude = models.FloatField()
    longitude = models.FloatField()
    fuel_type = models.CharField(max_length=50)
    price_per_gallon = models.FloatField()

    def __str__(self):
        return f"{self.station_name} - {self.city}"