# Fuel-Optimized Route API

A Django REST API that requests a driving route from OpenRouteService and proposes lower-cost fuel stops using station prices loaded from CSV.

## How the planner works

```text
coordinates + vehicle range/MPG
              |
              v
     OpenRouteService route
              |
              v
 decode polyline and track range
              |
              v
 choose the cheapest nearby station
```

The planner follows the returned polyline, reduces the remaining vehicle range per segment, and searches near the current route point when the configured 50-mile safety buffer is reached. If no station is found within 50 miles, it retries within 100 miles.

This is a greedy route-following heuristic. It does not solve global route-and-fuel optimization, model detour distance, or guarantee the cheapest possible trip.

## API

`POST /api/route/`

```json
{
  "start_lat": 34.0522,
  "start_lng": -118.2437,
  "end_lat": 36.1699,
  "end_lng": -115.1398,
  "vehicle_mpg": 28,
  "tank_range_miles": 360
}
```

The response contains decoded route coordinates, selected fuel stops, total route distance, and estimated fuel cost. OpenRouteService timeouts return `504`; upstream request failures return `502`.

## Local setup

Create `.env` in the project root:

```dotenv
DB_NAME=fuel_routes
DB_USER=postgres
DB_PASSWORD=change-me
ORS_API_KEY=change-me
```

Then prepare the service:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py load_fuel_data
python manage.py runserver
```

The loader reads `fuel_prices_sample.csv`. PostgreSQL and an OpenRouteService API key are required.

## Project map

- `api/views.py` — route request, polyline traversal, station selection, and cost estimate.
- `api/models.py` — fuel station records.
- `api/management/commands/load_fuel_data.py` — CSV import.
- `map_API/settings.py` — Django, database, and OpenRouteService configuration.

## Verification and design boundaries

- `api/tests.py` does not contain behavioral coverage.
- Station lookup first narrows by a latitude/longitude box and then applies haversine distance in Python.
- Estimated cost uses the selected or globally cheapest available price for the final segment; it is not a receipt-level simulation.
- Coordinate bounds, positive MPG, and positive range are not fully validated by the serializer.

## Next improvements

1. Validate coordinate ranges and positive vehicle inputs.
2. Isolate the route provider and planner for deterministic tests.
3. Include detour distance and station reachability in stop selection.
4. Move all development secrets and host settings behind environment configuration.
