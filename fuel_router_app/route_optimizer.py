import requests
from django.core.cache import cache
from typing import List, Dict, Tuple, Union, Optional
from .models import FuelStation
from geopy.distance import geodesic


class RouteOptimizer:
    def __init__(self):
        # Using public OSRM instance - you can also host your own
        self.OSRM_BASE_URL = 'http://router.project-osrm.org'
        self.NOMINATIM_BASE_URL = 'https://nominatim.openstreetmap.org'

    def geocode_location(self, location: str) -> Tuple[Optional[float], Optional[float]]:
        """Convert location string to coordinates using Nominatim"""
        url = f'{self.NOMINATIM_BASE_URL}/search'
        params = {
            'q': location,
            'format': 'json',
            'limit': 10,
            'countrycodes': 'us'  # Limit to USA
        }
        headers = {
            'User-Agent': 'RouteOptimizer/1.0'
        }
        response = requests.get(url, params=params, headers=headers)
        if response.status_code != 200:
            raise ValueError(f"Nominatim API request failed with status code {response.status_code}")

        data = response.json()
        if not data:
            return None, None

        # Extract coordinates from the first non-empty result
        for result in data:
            if 'lat' in result and 'lon' in result:
                return float(result['lat']), float(result['lon'])

        return None, None

    def get_route(self, start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> Dict[str, Union[float, List]]:
        """Get route using OSRM"""

        # Get route from OSRM
        url = f'{self.OSRM_BASE_URL}/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}'
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'steps': 'true'
        }
        response = requests.get(url, params=params)
        data = response.json()

        if data['code'] != 'Ok':
            raise ValueError("Could not calculate route")

        route = data['routes'][0]

        # Decode the polyline to get route points
        coordinates = route['geometry']['coordinates']

        return {
            'distance': route['distance'] / 1609.34,  # Convert meters to miles
            'duration': route['duration'] / 3600,  # Convert seconds to hours
            'geometry': coordinates,
            'steps': route['legs'][0]['steps']
        }


    def calculate_distance(self, point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
        """Check the cache for a pre-calculated distance or calculate and cache it."""

        cache_key = f"distance_{point1[0]}_{point1[1]}_{point2[0]}_{point2[1]}"
        cached_distance = cache.get(cache_key)

        if cached_distance is not None:
            return cached_distance

        # If the distance is not in cache, calculate it
        distance = geodesic(point1, point2).miles

        # Cache the calculated distance for future use (expire in 24 hours)
        cache.set(cache_key, distance, timeout=86400)
        return distance
    

    def find_optimal_fuel_stops(
            self,
            start_coords: Tuple[float, float],
            end_coords: Tuple[float, float],
            route_coordinates: List[List[float]],
            total_distance: float,
            tank_range: float,
            mpg: float
    ) -> Dict[str, Union[List[Dict[str, Union[str, float, Dict[str, float]]]], float]]:
        """Find optimal fuel stops along the route."""

        # Initialize variables
        fuel_stops = []
        remaining_range = tank_range
        last_stop_coords = start_coords
        stations = FuelStation.objects.all()

        # Sample points every 50 miles
        """
        The route is sampled at intervals (every ~50 miles) to reduce computational overhead by considering only key
        points instead of every point along the route.
        """
        sample_interval = max(1, len(route_coordinates) // int(total_distance / 50))
        sampled_points = route_coordinates[::sample_interval]

        for i, point in enumerate(sampled_points):
            # Calculate progress along route
            progress = i / len(sampled_points) * total_distance

            # If we're running low on fuel (25% of tank range remaining)
            """
            The car's fuel tank range is tracked, and when it drops below 25% of its capacity,
            nearby fuel stations are searched.
            """
            if remaining_range < (tank_range * 0.25) and progress < total_distance:
                # Find nearby stations
                nearby_stations = []
                """
                For each critical point on the route, nearby fuel stations are identified
                within a 20% radius of the tank range.
                """
                search_radius = tank_range * 0.2  # Look within 20% of tank range

                for station in stations:
                    distance = self.calculate_distance((point[1], point[0]), (station.lat, station.lon))

                    if distance <= search_radius:
                        # Calculate deviation from route

                        """
                        Deviation measures how much a fuel station deviates from the most direct route between the
                        current point on the route and the destination (end coordinates). The goal is to penalize
                        stations that cause unnecessary detours, as those will increase the overall trip distance
                        and fuel costs.

                        Formula:
                        D(start to station): Distance from Current Point to Fuel Station
                        D(station to end): Distance from Fuel Station to Destination
                        D(start to end): Direct Distance from Current Point to Destination

                        Deviation (Detour): (D(start to station) + D(station to end)) - D(start to end)
                        """
                        deviation = (
                            (self.calculate_distance((point[1], point[0]), (station.lat, station.lon)) +
                             self.calculate_distance((station.lat, station.lon), end_coords)) -
                            self.calculate_distance((point[1], point[0]), end_coords)
                        )

                        # Score based on price and deviation
                        # Lower is better
                        score = float(station.retail_price) + (deviation * 0.1)  # Penalty for deviation
                        nearby_stations.append({
                            'station': station,
                            'distance': distance,
                            'deviation': deviation,
                            'score': score
                        })
                """
                The "best" station is selected based on a scoring system:
                    1. Fuel price: Lower prices are preferred.
                    2. Route deviation: Stations that deviate less from the direct route are favored
                        (to minimize detour cost).
                """
                if nearby_stations:
                    best_station = min(nearby_stations, key=lambda x: x['score'])

                    # Calculate gallons needed
                    distance_since_last = self.calculate_distance(last_stop_coords, (
                        best_station['station'].lat, best_station['station'].lon))

                    gallons_needed = distance_since_last / mpg

                    fuel_stops.append({
                        'station_id': best_station['station'].opis_id,
                        'name': best_station['station'].name,
                        'location': {
                            'lat': best_station['station'].lat,
                            'lng': best_station['station'].lon
                        },
                        'price': float(best_station['station'].retail_price),
                        'distance_from_start': progress,
                        'gallons': gallons_needed,
                        'cost': float(best_station['station'].retail_price) * gallons_needed
                    })

                    # Update tracking variables
                    last_stop_coords = (best_station['station'].lat, best_station['station'].lon)
                    remaining_range = tank_range

            # Update remaining range
            if i > 0:
                distance_covered = self.calculate_distance(
                    (sampled_points[i - 1][1], sampled_points[i - 1][0]),
                    (point[1], point[0])
                )
                remaining_range -= distance_covered

        total_cost = sum(stop['cost'] for stop in fuel_stops)

        return {
            'fuel_stops': fuel_stops,
            'total_cost': total_cost,
            'total_distance': total_distance
        }

    def get_stop_details(self, stops: List[Dict]) -> Dict:
        """Get detailed information about the fuel stops"""

        return {
            'number_of_stops': len(stops),
            'total_gallons': sum(stop['gallons'] for stop in stops),
            'average_price': sum(stop['price'] for stop in stops) / len(stops) if stops else 0,
            'stops': stops
        }