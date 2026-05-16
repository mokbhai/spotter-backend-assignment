# Spotter Backend Assignment

Django REST API for route fuel planning. It calculates a driving route, selects
fuel stops from the provided CSV fuel-price dataset, and estimates gallons and
fuel cost for the trip.

## Demo Walkthrough

<iframe
  src="https://www.loom.com/embed/5f27a9d24cbb431c9951f8a87ad63386"
  width="100%"
  height="420"
  frameborder="0"
  webkitallowfullscreen
  mozallowfullscreen
  allowfullscreen>
</iframe>

If your Markdown viewer does not render iframes, watch the walkthrough here:
<https://www.loom.com/share/5f27a9d24cbb431c9951f8a87ad63386>

## Project Links

- Live demo: <https://spotter.mokshit.jainparichay.in/>

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
make install
make migrate
```

## Import Fuel Prices

Load the provided CSV without calling the external Census batch geocoder:

```bash
make import-fuel-prices
```

Load the CSV and geocode pending stations through the Census batch geocoder when
network access is acceptable:

```bash
make import-fuel-prices-geocode
```

The import command reads the CSV, creates or updates fuel station price/name
data, and preserves existing station geocoding state when those rows already
have coordinates. With `--skip-geocoding`, it skips the external Census batch
call but still approximates missing station coordinates from the local GeoNames
city/state dataset. Without `--skip-geocoding`, it first geocodes stations still
marked as pending through Census, then applies the same city/state fallback for
unmatched rows so highway-style station addresses do not leave large route
coverage gaps.

## Run Server

```bash
make run
```

Runtime settings can be overridden with environment variables:

- `SPOTTER_SECRET_KEY`
- `SPOTTER_DEBUG`
- `SPOTTER_ALLOWED_HOSTS`
- `SPOTTER_FUEL_PLAN_THROTTLE`

## Run Production Server With Docker

Build the image:

```bash
make docker-build
```

Run the API with Gunicorn:

```bash
make docker-run SPOTTER_SECRET_KEY='replace-this-secret'
```

By default, the container runs migrations, imports the provided fuel-price CSV
with `--skip-geocoding`, and then starts Gunicorn. To run without importing on
startup:

```bash
make docker-run-no-import SPOTTER_SECRET_KEY='replace-this-secret'
```

To import and geocode pending stations through the Census batch geocoder on
startup:

```bash
make docker-run-import-geocode SPOTTER_SECRET_KEY='replace-this-secret'
```

The container serves the API at `http://127.0.0.1:8000/api/routes/fuel-plan/`
and the architecture console at
`http://127.0.0.1:8000/static/routing/architecture-api-demo.html`.

Useful Make variables:

- `PORT`: port used inside the Django/Gunicorn process. Defaults to `8000`.
- `HOST_PORT`: host port published by Docker. Defaults to `8000`.
- `IMAGE`: Docker image name. Defaults to `spotter-backend`.
- `TAG`: Docker image tag. Defaults to `local`.
- `DATA_VOLUME`: Docker volume mounted at `/app/data`. Defaults to `spotter-data`.
- `SPOTTER_ALLOWED_HOSTS`: comma-separated Django allowed hosts.
- `SPOTTER_SECRET_KEY`: required production Django secret key.
- `SPOTTER_RUN_MIGRATIONS`: run migrations on container startup. Defaults to `true`.
- `SPOTTER_IMPORT_FUEL_PRICES`: import the bundled fuel CSV on startup. Defaults to `true`.
- `SPOTTER_IMPORT_FUEL_PRICES_GEOCODE`: geocode pending stations during startup import. Defaults to `false`.

## API

POST route fuel-plan requests to:

```text
/api/routes/fuel-plan/
```

An interactive architecture and API console is available when the Django
development server is running:

```text
http://127.0.0.1:8000/static/routing/architecture-api-demo.html
```

Coordinate input is the fastest path because it does not require request-time
geocoding:

```bash
curl -X POST http://127.0.0.1:8000/api/routes/fuel-plan/ \
  -H 'Content-Type: application/json' \
  -d '{
    "start": {"lat": 30.2672, "lng": -97.7431},
    "destination": {"lat": 39.7392, "lng": -104.9903}
  }'
```

Address-string input is also supported. Simple `City, ST` requests resolve from
the local GeoNames city dataset and are cached locally; other address strings
use the Census Geocoder at request time and are cached locally:

```bash
curl -X POST http://127.0.0.1:8000/api/routes/fuel-plan/ \
  -H 'Content-Type: application/json' \
  -d '{
    "start": "Austin, TX",
    "destination": "Denver, CO"
  }'
```

Successful responses include:

- `route`: route distance and full OSRM GeoJSON `LineString` geometry.
- `fuel_plan`: selected stops, gallons, cost, price per gallon, total gallons,
  total cost, range, MPG, and currency.
- `fuel_plan.starting_fuel_assumption`: an explicit estimate for fuel used
  before the first available dataset station when no station is close to the
  origin segment. This keeps stop-level gallons physically meaningful while
  keeping total gallons and total cost tied to the full route.
- `warnings`: planner warnings such as arrival fuel notes.
- `metadata`: provider metadata, including the routing provider.

## Postman Collection

A Postman collection is available at `Spotter_Backend_API.postman_collection.json` with pre-configured requests for:

- Fuel plan creation with coordinate inputs
- Fuel plan creation with address inputs
- Fuel plan creation with custom parameters

Import the collection into Postman and set the `base_url` variable to your server URL (default: `http://127.0.0.1:8000`).

## Tests

```bash
make test
```

Automated tests mock external services and should not depend on live OSRM or
Census API availability.

## External Services

- OSRM route API for driving route calculation.
- Census Geocoder for street/freeform address geocoding and batch station
  geocoding.
- GeoNames city data for request-time `City, ST` input and import-time
  city/state station-coordinate fallback.

## Important Assumptions

- Vehicle maximum range is 500 miles by default.
- Fuel economy is 10 MPG by default.
- The planner does not give free starting fuel credit; required gallons are
  purchased from selected stops.
- Fuel stations are selected from active imported rows with either exact Census
  coordinates or city/state fallback coordinates.
- Routes can still return `no_feasible_fuel_plan` when the provided fuel-price
  dataset has no station coverage within the requested vehicle range.
