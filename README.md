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

## Example Map
Below is an example of the route map with marked fuel stops:

![Route Map](https://github.com/UzairNaeem3/route-planner-with-fuel/blob/master/LA_NY.png)

## How It Works
1. **Input**: Users provide a start and finish location within the USA.
2. **Route Calculation**: The API calculates the best route using a free map and routing service.
3. **Fuel Stop Optimization**:
   - The route is divided into 500-mile segments (the maximum vehicle range).
   - Optimal refueling stops are selected within each segment based on fuel prices.
4. **Output**:
   - A map showing the route and marked refueling stops.
   - A JSON response summarizing the total fuel cost and other details.

## Prerequisites
- Python 3.7+
- Install dependencies listed in `requirements.txt`.


## Setup Instructions
1. Clone the repository:
   ```bash
   git clone https://github.com/UzairNaeem3/route-planner-with-fuel.git
   cd route-planner-with-fuel
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the API server:
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
       "start_location": "New York, NY, USA",
       "finish_location": "Los Angeles, CA, USA"
   }
   ```
   
   **Response**:
   ```json
   {
    "route_coordinates": ["Coordinates between start and end location"],
    "map_url": "URL-to-route-map",
    "fuel_stops": ["Fuel stops along the route"],
    "total_cost": 123.45,
    "total_distance": 500.0
}
   ```

## Fuel Price Dataset
- The API uses a provided dataset containing fuel prices across various locations in the USA. Ensure the dataset is placed in the specified folder before running the server.

## Technologies Used
- **Backend**: Django
- **Mapping API**: Free map and routing API (e.g., OpenRouteService, MapQuest, or similar)

## Future Enhancements
- Support for different fuel efficiency values.
- Dynamic vehicle range input.
- Enhanced UI for route and fuel stop visualization.
- Integration with real-time fuel price APIs.


## Contributing
Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

Feel free to reach out with questions or suggestions!
