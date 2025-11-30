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
        
        # Optimize: Filter stations by bounding box of the route
        lats = [p[1] for p in route_coordinates]
        lons = [p[0] for p in route_coordinates]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        
        # Add a buffer (approx 50 miles ~ 0.7 degrees)
        buffer = 1.0 
        stations = list(FuelStation.objects.filter(
            lat__gte=min_lat - buffer,
            lat__lte=max_lat + buffer,
            lon__gte=min_lon - buffer,
            lon__lte=max_lon + buffer
        ))

        # Sample points every 50 miles
        sample_interval = max(1, len(route_coordinates) // int(total_distance / 50)) if int(total_distance / 50) > 0 else 1
        sampled_points = route_coordinates[::sample_interval]
        
        # Ensure the last point is included if not already
        if sampled_points[-1] != route_coordinates[-1]:
            sampled_points.append(route_coordinates[-1])

        i = 0
        while i < len(sampled_points):
            point = sampled_points[i]
            # Current point coords (lat, lon)
            current_coords = (point[1], point[0])
            
            # Calculate distance from last check (or start)
            if i > 0:
                prev_point = sampled_points[i-1]
                dist_from_prev = self.calculate_distance((prev_point[1], prev_point[0]), current_coords)
                remaining_range -= dist_from_prev
            
            # Calculate progress
            dist_from_start = self.calculate_distance(start_coords, current_coords)

            # Check if we need fuel
            # Strategy: Look for fuel when we are below 40% OR if we can't reach the next sample point
            # Estimate distance to next sample point (approx 50 miles)
            dist_to_next = 50 
            if i < len(sampled_points) - 1:
                 next_point = sampled_points[i+1]
                 dist_to_next = self.calculate_distance(current_coords, (next_point[1], next_point[0]))

            if remaining_range < (tank_range * 0.40) or remaining_range < (dist_to_next + 20):
                
                # If we are close to destination, check if we can make it
                dist_to_end = self.calculate_distance(current_coords, end_coords)
                if remaining_range >= dist_to_end:
                    i += 1
                    continue # We can make it!

                # Search for stations
                # Search radius: We should search up to our remaining range.
                # We use a slight buffer (95%) to account for road vs geodesic differences, 
                # but if we are critical, we take the risk and search full range.
                
                search_radius = remaining_range * 0.95
                if remaining_range < 50:
                    search_radius = remaining_range # Desperate times

                nearby_stations = []
                for station in stations:
                    dist_to_station = self.calculate_distance(current_coords, (station.lat, station.lon))
                    
                    if dist_to_station <= search_radius:
                        # Deviation logic
                        deviation = (
                            (dist_to_station +
                             self.calculate_distance((station.lat, station.lon), end_coords)) -
                            dist_to_end
                        )
                        
                        # Score: Price + Deviation penalty
                        # We want low price and low deviation.
                        # Weight deviation: 1 mile deviation ~= $0.10 per gallon penalty? 
                        # This is heuristic.
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
                    
                    # Calculate gallons needed to fill up
                    # We assume we fill up to full tank
                    # Gallons used since last fill = (Tank Capacity - Remaining at station)
                    # But wait, we are at 'current_coords', station is 'dist_to_station' away.
                    # We arrive at station with: remaining_range - best_station['distance']
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
                    
                    # Update state
                    last_stop_coords = (station_obj.lat, station_obj.lon)
                    
                    # Resume logic: Find the closest sample point to the station
                    best_k = i
                    min_d = float('inf')
                    # Search forward from current point
                    for k in range(i, len(sampled_points)):
                         pt = sampled_points[k]
                         d = self.calculate_distance((pt[1], pt[0]), (station_obj.lat, station_obj.lon))
                         if d < min_d:
                             min_d = d
                             best_k = k
                         else:
                             # If distance starts increasing, we are moving away
                             if d > min_d + 50: # Buffer
                                 break
                    
                    if best_k < len(sampled_points) - 1:
                        # Resume from best_k + 1
                        i = best_k + 1
                        
                        # Calculate remaining range at best_k + 1
                        # It is Tank Range - Dist(Station, best_k+1)
                        next_pt = sampled_points[i]
                        dist_station_to_next = self.calculate_distance(
                            (station_obj.lat, station_obj.lon),
                            (next_pt[1], next_pt[0])
                        )
                        
                        # We need to trick the loop into setting this remaining_range.
                        # The loop does: remaining_range -= dist_from_prev
                        # We want remaining_range to be (Tank - Dist_Station_Next) AFTER the loop subtraction.
                        # So we set remaining_range = Tank - Dist_Station_Next + Dist_Prev_Next
                        
                        prev_pt_resume = sampled_points[i-1]
                        dist_prev_resume_to_next = self.calculate_distance(
                            (prev_pt_resume[1], prev_pt_resume[0]),
                            (next_pt[1], next_pt[0])
                        )
                        remaining_range = tank_range - dist_station_to_next + dist_prev_resume_to_next
                        
                        continue
                    else:
                        # We are at the end of the route
                        remaining_range = tank_range # Full tank at end?
                        i += 1
                        continue

                else:
                    # No stations found!
                    if remaining_range < 20:
                        raise ValueError(f"Unable to find fuel stations! Stranded at {current_coords} with {remaining_range:.2f} miles range.")
            
            i += 1

        # Calculate final leg cost
        dist_last_stop_to_end = self.calculate_distance(last_stop_coords, end_coords)
        gallons_final = dist_last_stop_to_end / mpg
        
        # Price for final leg? Use average of paid prices or last stop price.
        if fuel_stops:
            final_price = fuel_stops[-1]['price']
        else:
            # No stops needed (short trip), use average of all stations or a default?
            # Or maybe we started with a full tank and didn't pay for it?
            # The prompt says "return total money spent on fuel".
            # Usually implies cost of the trip. Let's charge for the fuel used.
            # We'll use a national average or just the first station we find?
            # Let's use the average price of stations in our bounding box as a fallback.
            if stations:
                avg_price = sum(float(s.retail_price) for s in stations) / len(stations)
                final_price = avg_price
            else:
                final_price = 3.50 # Fallback
        
        final_cost = final_price * gallons_final
        
        # If we want to include the final leg in the "total cost" but not as a "stop":
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