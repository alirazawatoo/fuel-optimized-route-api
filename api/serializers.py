from rest_framework import serializers

class RouteRequestSerializer(serializers.Serializer):
    start_lat = serializers.FloatField()
    start_lng = serializers.FloatField()
    end_lat = serializers.FloatField()
    end_lng = serializers.FloatField()
    vehicle_mpg = serializers.FloatField(default=10)
    tank_range_miles = serializers.FloatField(default=500)

    def validate(self, data):
        if (data['start_lat'] == data['end_lat'] and 
            data['start_lng'] == data['end_lng']):
            raise serializers.ValidationError("Start and end locations must be different")
        return data