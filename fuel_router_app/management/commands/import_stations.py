import csv
import requests
from itertools import islice
from django.conf import settings
from django.core.management.base import BaseCommand
from fuel_router_app.models import FuelStation


class Command(BaseCommand):
    help = 'Import fuel stations from CSV file in batches'

    def handle(self, *args, **options):
        base_dir = settings.BASE_DIR
        fuel_prices_csv = base_dir / 'fuel-prices-for-be-assessment.csv'

        with open(fuel_prices_csv, mode='r') as file:
            reader = csv.DictReader(file)
            start = 0
            limit = 100
            while True:
                print(f"processing rows from: {start*limit}")
                batch = list(islice(reader, limit))  # Read 100 rows at a time
                if not batch:
                    break
                
                self.process_batch(batch)
                start+=1

    def process_batch(self, batch):
        for stop in batch:
            if FuelStation.objects.filter(opis_id=stop["OPIS Truckstop ID"]).exists():
                print("Id already exists")
                continue
            
            print(f"process shop : {stop['OPIS Truckstop ID']}")
            formatted_location = stop['Address'].replace("EXIT", "").replace("&", "and").replace("  ", " ").strip()
            lat, lon = None, None

            for attempt in [
                f"{formatted_location}, {stop['City']}, {stop['State']}, USA",
                f"{stop['Address'].replace('EXIT', '').strip()}, {stop['City']}, {stop['State']}, USA",
                f"{stop['City']}, {stop['State']}, USA"
            ]:
                lat, lon = self.geocode_location(attempt)
                if lat and lon:
                    break  # Exit once valid coordinates are found

            if lat is not None and lon is not None:
                FuelStation.objects.create(
                    opis_id=stop['OPIS Truckstop ID'],
                    name=stop['Truckstop Name'],
                    address=stop['Address'],
                    city=stop['City'],
                    state=stop['State'],
                    rack_id=stop['Rack ID'],
                    lat=lat,
                    lon=lon,
                    retail_price=stop['Retail Price'],
                )
                
            else:
                print(f"Failed to geocode location: {formatted_location}")

        print(f"Imported fuel stations successfully.")

    def geocode_location(self, location):
        url = 'https://nominatim.openstreetmap.org/search'
        params = {
            'q': location,
            'format': 'json',
            'limit': 10,
            'countrycodes': 'us'
        }
        headers = {'User-Agent': 'RouteOptimizer/1.0'}
        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            if data:
                for result in data:
                    if 'lat' in result and 'lon' in result:
                        return float(result['lat']), float(result['lon'])
        except requests.RequestException as e:
            print(f"Geocoding request failed: {e}")
        return None, None