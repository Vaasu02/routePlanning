import requests
from django.core.cache import cache
from typing import List, Dict, Tuple, Union, Optional
from .models import FuelStation
from geopy.distance import geodesic


class RouteOptimizer:
    def __init__(self):
        
        self.OSRM_BASE_URL = 'http://router.project-osrm.org'
        self.NOMINATIM_BASE_URL = 'https://nominatim.openstreetmap.org'

    def geocode_location(self, location: str) -> Tuple[Optional[float], Optional[float]]:
        """Convert location string to coordinates using Nominatim"""
        url = f'{self.NOMINATIM_BASE_URL}/search'
        params = {
            'q': location,
            'format': 'json',
            'limit': 10,
            'countrycodes': 'us'  
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

        
        for result in data:
            if 'lat' in result and 'lon' in result:
                return float(result['lat']), float(result['lon'])

        return None, None

    def get_route(self, start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> Dict[str, Union[float, List]]:
        """Get route using OSRM"""

        
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

        
        coordinates = route['geometry']['coordinates']

        return {
            'distance': route['distance'] / 1609.34,  
            'geometry': coordinates,
            'steps': route['legs'][0]['steps']
        }


    def calculate_distance(self, point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
        """Check the cache for a pre-calculated distance or calculate and cache it."""

        cache_key = f"distance_{point1[0]}_{point1[1]}_{point2[0]}_{point2[1]}"
        cached_distance = cache.get(cache_key)

        if cached_distance is not None:
            return cached_distance

        
        distance = geodesic(point1, point2).miles

        
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

        
        fuel_stops = []
        remaining_range = tank_range
        last_stop_coords = start_coords
        
        
        lats = [p[1] for p in route_coordinates]
        lons = [p[0] for p in route_coordinates]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        
        
        buffer = 1.0 
        stations = list(FuelStation.objects.filter(
            lat__gte=min_lat - buffer,
            lat__lte=max_lat + buffer,
            lon__gte=min_lon - buffer,
            lon__lte=max_lon + buffer
        ))

        
        sample_interval = max(1, len(route_coordinates) // int(total_distance / 50)) if int(total_distance / 50) > 0 else 1
        sampled_points = route_coordinates[::sample_interval]
        
       
        if sampled_points[-1] != route_coordinates[-1]:
            sampled_points.append(route_coordinates[-1])

        i = 0
        while i < len(sampled_points):
            point = sampled_points[i]
            
            current_coords = (point[1], point[0])
            
           
            if i > 0:
                prev_point = sampled_points[i-1]
                dist_from_prev = self.calculate_distance((prev_point[1], prev_point[0]), current_coords)
                remaining_range -= dist_from_prev
            
            
            dist_from_start = self.calculate_distance(start_coords, current_coords)

           
            dist_to_next = 50 
            if i < len(sampled_points) - 1:
                 next_point = sampled_points[i+1]
                 dist_to_next = self.calculate_distance(current_coords, (next_point[1], next_point[0]))

            if remaining_range < (tank_range * 0.40) or remaining_range < (dist_to_next + 20):
                
                
                dist_to_end = self.calculate_distance(current_coords, end_coords)
                if remaining_range >= dist_to_end:
                    i += 1
                    continue 

                
                
                search_radius = remaining_range * 0.95
                if remaining_range < 50:
                    search_radius = remaining_range 
                nearby_stations = []
                for station in stations:
                    dist_to_station = self.calculate_distance(current_coords, (station.lat, station.lon))
                    
                    if dist_to_station <= search_radius:
                       
                        deviation = (
                            (dist_to_station +
                             self.calculate_distance((station.lat, station.lon), end_coords)) -
                            dist_to_end
                        )
                        
                        
                        score = float(station.retail_price) + (deviation * 0.05)
                        nearby_stations.append({
                            'station': station,
                            'distance': dist_to_station,
                            'deviation': deviation,
                            'score': score
                        })

                if nearby_stations:
                    best_station = min(nearby_stations, key=lambda x: x['score'])
                    station_obj = best_station['station']
                    
                    range_at_station = remaining_range - best_station['distance']
                    gallons_to_fill = (tank_range - range_at_station) / mpg
                    
                    # Cost for this fill-up
                    cost = float(station_obj.retail_price) * gallons_to_fill
                    
                    fuel_stops.append({
                        'station_id': station_obj.opis_id,
                        'name': station_obj.name,
                        'location': {
                            'lat': station_obj.lat,
                            'lng': station_obj.lon
                        },
                        'price': float(station_obj.retail_price),
                        'distance_from_start': dist_from_start + best_station['distance'], # Approx
                        'gallons': gallons_to_fill,
                        'cost': cost
                    })
                    
                    
                    last_stop_coords = (station_obj.lat, station_obj.lon)
                    
                    
                    best_k = i
                    min_d = float('inf')
                   
                    for k in range(i, len(sampled_points)):
                         pt = sampled_points[k]
                         d = self.calculate_distance((pt[1], pt[0]), (station_obj.lat, station_obj.lon))
                         if d < min_d:
                             min_d = d
                             best_k = k
                         else:
                            
                             if d > min_d + 50: 
                                 break
                    
                    if best_k < len(sampled_points) - 1:
                        
                        i = best_k + 1
                        
                        
                        next_pt = sampled_points[i]
                        dist_station_to_next = self.calculate_distance(
                            (station_obj.lat, station_obj.lon),
                            (next_pt[1], next_pt[0])
                        )
                        
                        
                        
                        prev_pt_resume = sampled_points[i-1]
                        dist_prev_resume_to_next = self.calculate_distance(
                            (prev_pt_resume[1], prev_pt_resume[0]),
                            (next_pt[1], next_pt[0])
                        )
                        remaining_range = tank_range - dist_station_to_next + dist_prev_resume_to_next
                        
                        continue
                    else:
                        
                        remaining_range = tank_range 
                        i += 1
                        continue

                else:
                    
                    if remaining_range < 20:
                        raise ValueError(f"Unable to find fuel stations! Stranded at {current_coords} with {remaining_range:.2f} miles range.")
            
            i += 1

        
        dist_last_stop_to_end = self.calculate_distance(last_stop_coords, end_coords)
        gallons_final = dist_last_stop_to_end / mpg
        
        
        if fuel_stops:
            final_price = fuel_stops[-1]['price']
        else:
            
            if stations:
                avg_price = sum(float(s.retail_price) for s in stations) / len(stations)
                final_price = avg_price
            else:
                final_price = 3.50
        
        final_cost = final_price * gallons_final
        
        
        total_cost = sum(stop['cost'] for stop in fuel_stops) + final_cost

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