from rest_framework import serializers


class RouteResponseSerializer(serializers.Serializer):
    route_coordinates = serializers.ListField(child=serializers.ListField(child=serializers.FloatField()))
    fuel_stops = serializers.ListField(child=serializers.DictField())
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=4)
    total_distance = serializers.FloatField()
    map_url = serializers.CharField()


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(max_length=255)
    end = serializers.CharField(max_length=255)