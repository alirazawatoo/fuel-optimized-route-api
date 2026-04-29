from rest_framework import serializers
import math

class RouteRequestSerializer(serializers.Serializer):
    start_lat = serializers.FloatField()
    start_lng = serializers.FloatField()
    end_lat = serializers.FloatField()
    end_lng = serializers.FloatField()
    vehicle_mpg = serializers.FloatField(default=10)
    tank_range_miles = serializers.FloatField(default=500)

    def validate(self, data):
        for key, value in data.items():
            if not math.isfinite(value):
                raise serializers.ValidationError({key: 'Use a finite number'})
        for key in ['start_lat', 'end_lat']:
            if not -90 <= data[key] <= 90:
                raise serializers.ValidationError({key: 'Use latitude -90 to 90'})
        for key in ['start_lng', 'end_lng']:
            if not -180 <= data[key] <= 180:
                raise serializers.ValidationError({key: 'Use longitude -180 to 180'})
        if not 1 <= data['vehicle_mpg'] <= 200:
            raise serializers.ValidationError({'vehicle_mpg': 'Use 1 to 200 MPG'})
        if not 51 <= data['tank_range_miles'] <= 2000:
            raise serializers.ValidationError({'tank_range_miles': 'Use a range of 51 to 2000 miles'})
        if (data['start_lat'] == data['end_lat'] and 
            data['start_lng'] == data['end_lng']):
            raise serializers.ValidationError("Start and end locations must be different")
        return data