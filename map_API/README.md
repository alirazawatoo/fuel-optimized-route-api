# What would this route cost in fuel?

This Django REST endpoint combines an OpenRouteService route with a local table of station prices. It returns route coordinates, selected fuel-stop candidates, distance, and a fuel-cost estimate.

The current method walks sampled route segments, normalizes their straight-line lengths to the provider's reported driving distance, and searches for cheaper nearby stations when remaining range falls below a 50-mile buffer. It assumes a full starting tank.

It does **not** establish a globally cheapest plan. It does not route detours to stations, validate road access, choose fuel grade, model tank purchase amounts, or prove a station is reachable by road. Sparse geometry that exceeds remaining range is rejected instead of producing an apparently feasible plan. Do not use this prototype as navigation or a guarantee against running out of fuel.

## Flow and layout

```text
POST /api/route/ → finite coordinate/vehicle validation → ORS Directions
    → decode route → sample station candidates in PostgreSQL → estimate
CSV → validated station identity and price → update existing prices
```

- `api/serializers.py`: coordinate bounds, positive bounded MPG/range.
- `api/views.py`: routing request, segment heuristic, fuel estimate.
- `api/management/commands/load_fuel_data.py`: atomic CSV import, preserving ZIP-code strings.
- `fuel_prices_sample.csv`: demonstration rows, not live prices or verified station coverage.

## Run locally

Use a Python version supported by the declared Django 6 dependencies and a local PostgreSQL database. From this directory:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set your own `DB_NAME`, `DB_USER`, `DB_PASSWORD` and `ORS_API_KEY`. The API key must belong to you. Local `DJANGO_DEBUG=true` creates a temporary signing key when none is supplied; with debug disabled, an explicit private `DJANGO_SECRET_KEY` is required. Never commit these values.

```sh
python manage.py migrate
python manage.py load_fuel_data
python manage.py runserver 127.0.0.1:8000
```

The importer accepts `--path /path/to/stations.csv`. A station identity includes its name, location, coordinates and fuel type; importing a new price updates that identity. Existing duplicates from old imports need a separate data cleanup. The import does not delete unrelated stations.

## Request and response

```sh
curl http://127.0.0.1:8000/api/route/   -H 'Content-Type: application/json'   -d '{"start_lat":34.05,"start_lng":-118.24,"end_lat":34.15,"end_lng":-118.14,"vehicle_mpg":25,"tank_range_miles":400}'
```

The result has `route` as latitude/longitude pairs, `fuel_stops` with station names/coordinates/prices, `total_distance_miles`, and `total_fuel_cost`. No example dollar amount is presented as a verified journey result.

Validation accepts latitude -90–90, longitude -180–180, MPG 1–200, and tank range 51–2000 miles. Identical endpoints are rejected. Missing provider configuration or station prices returns 503; upstream failure or malformed data returns 502; timeout returns 504; insufficient route sampling for a reachable plan returns 422.

## Evidence and next steps

```sh
python manage.py test api --settings=map_API.test_settings
```

Six tests cover numeric bounds, a mocked short route, missing station data, malformed/sparse routes, safe provider errors, and repeat CSV imports. They were verified on an existing Django 4.2 test environment with in-memory SQLite and polyline 2.0.4; the declared Django 6/PostgreSQL stack and live ORS endpoint were not exercised.

Before hosting, add authentication and request/cost limits, cap upstream response bytes and aggregate database work, introduce spatial indexing and candidate prefetching, and evaluate the heuristic against a feasible-route reference solver. The current route can issue many station queries; offsets near the antimeridian need additional geographic handling. Prices are floats and the final segment uses a fallback station price, so the result is a rough consumption estimate rather than a record of purchases. No UI or map screenshot is claimed.
