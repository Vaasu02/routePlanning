# Route Optimization and Fuel Cost API

## Overview
This Django application provides an API designed to calculate and display:
1. The optimal route between a start and finish location within the USA.
2. Cost-effective fuel stops along the route, based on fuel prices.
3. The total fuel cost for the journey, considering the vehicle's fuel efficiency and range.

## Key Features
- Generates a route between the specified start and finish locations using a free map and routing API.
- Identifies optimal refueling stops along the route based on fuel prices.
- Calculates the total money spent on fuel for the journey based on:
  - Vehicle range: 500 miles per tank.
  - Fuel efficiency: 10 miles per gallon.
- Uses a provided fuel price dataset to determine refueling costs.

## How It Works
1. **Input**: Users provide a start and finish location within the USA.
2. **Route Calculation**: The API calculates the best route using a free map and routing service.
3. **Fuel Stop Optimization**:
   - The route is divided into 500-mile segments (the maximum vehicle range).
   - Optimal refueling stops are selected within each segment based on fuel prices.
4. **Output**:
   - A map showing the route and marked refueling stops.
   - A JSON response summarizing the total fuel cost and other details.


## Setup Instructions
1. Clone the repository:
   ```bash
   git clone https://github.com/Vaasu02/routePlanning.git
   cd routePlanning
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run migrations to create database tables:
   ```bash
   python manage.py migrate
   ```
5. Import fuel stations from the CSV:
   ```bash
   python manage.py import_stations
   ```
6. Run the API server:
   ```bash
   python manage.py runserver
   ```

## API Endpoints
### 1. **Calculate Route and Fuel Stops**
   **Endpoint**: `/api/plan-route/`
   
   **Method**: POST
   
   **Request Body**:
   ```json
   {
       "start": "Chicago, IL",
       "end": "Los Angeles, CA"
   }
   ```
   
   **Response**:
   ```json
   {
    "route_coordinates": [[-87.6298, 41.8781],...],
    "map_url": "/media/maps/map.html",
    "fuel_stops": [
        {
            "station_id": 192,
            "name": "Brew Stuart Truckstop",
            "location": {"lat": 41.496, "lng": -94.375},
            "price": 3.099,
            "distance_from_start": 350.14,
            "gallons": 35.29,
            "cost": 109.36
        },
        ...
    ],
    "total_cost": 690.17,
    "total_distance": 2017.92
   }
   ```



