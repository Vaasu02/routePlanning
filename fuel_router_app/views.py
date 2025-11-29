from rest_framework.views import APIView
from rest_framework.response import Response
from fuel_router_app.route_optimizer import RouteOptimizer
import folium
from fuel_router_app.serializers import RouteRequestSerializer, RouteResponseSerializer
from decimal import Decimal
from django.conf import settings
from folium.plugins import MarkerCluster
import os

map_file_path = settings.BASE_DIR / 'maps/map.html'


class RoutePlannerView(APIView):
    def post(self, request):
        # Validate request data using serializer
        request_serializer = RouteRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        start = request_serializer.validated_data['start']
        end = request_serializer.validated_data['end']
        route_service = RouteOptimizer()

        try:
            # Convert locations to coordinates
            start_lat, start_lon = route_service.geocode_location(start)
            end_lat, end_lon = route_service.geocode_location(end)

            # Get route from OSRM
            route_data = route_service.get_route(start_lat, start_lon, end_lat, end_lon)

            # Calculate optimal stops
            result = route_service.find_optimal_fuel_stops(
                (start_lat, start_lon), (end_lat, end_lon),
                route_data['geometry'], route_data['distance'], tank_range=500, mpg=10
            )

            # Generate map
            map_html = self.generate_map(route_data['geometry'], result['fuel_stops'])

            # Save map to a file
            os.makedirs(os.path.dirname(map_file_path), exist_ok=True)
            with open(map_file_path, 'w') as file:
                file.write(map_html)

            response_data = {
                'route_coordinates': route_data['geometry'],
                'fuel_stops': result['fuel_stops'],
                'total_cost': round(Decimal(result['total_cost']), 4),
                'total_distance': result['total_distance'],
                'map_url': str(map_file_path)
            }

            serializer = RouteResponseSerializer(data=response_data)
            serializer.is_valid(raise_exception=True)

            return Response(serializer.data)

        except Exception as e:
            return Response({'error': str(e)}, status=400)

    def generate_map(self, coordinates, fuel_stops):
        # Create map centered on route with Google Satellite view tile layer
        map_center = coordinates[len(coordinates) // 2]
        m = folium.Map(location=[map_center[1], map_center[0]], zoom_start=14)

        # Add route with a smoother Polyline
        folium.PolyLine(
            [(lat, lon) for lon, lat in coordinates],
            weight=5,
            color='blue',
            opacity=0.7
        ).add_to(m)

        # Marker Cluster for fuel stops
        marker_cluster = MarkerCluster().add_to(m)

        # Start marker (Green marker for start point)
        start_point = coordinates[0]  # First point in coordinates
        folium.Marker(
            [start_point[1], start_point[0]],
            tooltip="Start",
            popup="This is the start point!",
            icon=folium.Icon(color='green', icon='play')
        ).add_to(m)

        # Stop marker (Red marker for stop point)
        stop_point = coordinates[-1]  # Last point in coordinates
        folium.Marker(
            [stop_point[1], stop_point[0]],
            tooltip="End",
            popup="This is the stop point!",
            icon=folium.Icon(color='red', icon='stop')
        ).add_to(m)

        # Add fuel stops
        for stop in fuel_stops:
            folium.Marker(
                [stop['location']['lat'], stop['location']['lng']],
                tooltip=stop['name'],
                popup=f"{stop['name']}<br>Price: ${stop['price']}/gal",
                icon=folium.Icon(color='blue', icon='fa-gas-pump', prefix='fa')
            ).add_to(marker_cluster)

        return m._repr_html_()
