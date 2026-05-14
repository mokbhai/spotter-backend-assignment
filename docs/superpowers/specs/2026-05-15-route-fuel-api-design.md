# Route Fuel Stop API Design

## Goal

Build a Django REST API that accepts a start location and destination location within the USA, computes a drivable route, recommends cost-effective fuel stops along that route, and returns route geometry plus estimated fuel spend.

The API should be fast at request time and should avoid repeated calls to free third-party routing services. Fuel station prices come from `fuel-prices-for-be-assessment.csv`.

## Non-Goals

- Do not require user-entered start or destination locations to exist in the fuel-price dataset.
- Do not generate a raster map image on the backend.
- Do not call an external API for every fuel station during route requests.
- Do not optimize for live fuel-price updates unless a fresh CSV is imported.
- Do not build a frontend map UI for this phase.

## Key Assumptions

- The vehicle has a maximum range of 500 miles.
- The vehicle achieves 10 miles per gallon.
- A full tank therefore represents 50 gallons.
- The API will not credit pre-existing fuel in the tank. It will calculate the fuel that must be purchased for the trip distance using the selected stations. This makes total spend deterministic from the available fuel prices.
- The first purchase should be modeled at an eligible station near the origin route segment. If no origin-area station exists in the dataset, the service may use the cheapest reachable station within the first 500 miles, but the response must make that assumption visible in `warnings`.
- Fuel stops should be selected from known fuel stations with geocoded coordinates and retail prices from the CSV.
- A station can be used only if it is close enough to the computed route corridor.
- Default route corridor should be conservative, such as 10 miles from the route, with an optional request parameter to widen it up to a safe maximum.
- If the local fuel dataset cannot support a route within the 500-mile range constraint, the API must return a clear failure instead of fabricating stops.

## External Services

### Routing

Use OSRM's route API for route calculation. It can return route geometry in GeoJSON format and route distance in meters. Runtime route requests should make one routing call after coordinates are available.

Recommended endpoint shape:

```text
GET https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson&steps=false
```

### Geocoding

Use the U.S. Census Geocoder batch endpoint during the station import/enrichment process. The CSV has 8,151 data rows, which fits within the Census batch limit of 10,000 records.

For user-entered start and destination strings, use a lightweight request-time geocoder. Prefer accepting coordinates directly to avoid extra external calls. If address strings are provided, use the Census Geocoder or another free geocoder with caching.

## Data Model

### FuelStation

Stores imported and enriched fuel-station data.

Fields:

- `opis_truckstop_id`: original OPIS truckstop ID.
- `name`: truckstop name.
- `address`: street/highway address from CSV.
- `city`: city from CSV.
- `state`: state code from CSV.
- `rack_id`: rack ID from CSV.
- `retail_price`: decimal dollars per gallon.
- `latitude`: nullable decimal coordinate.
- `longitude`: nullable decimal coordinate.
- `geocoding_status`: `pending`, `matched`, `unmatched`, or `failed`.
- `geocoding_score`: optional confidence/quality metadata when available.
- `source_row_hash`: hash used to detect changed CSV rows.
- `is_active`: true only when station has usable coordinates and price.
- `created_at`, `updated_at`.

Indexes:

- `(state, city)` for admin/debug filtering.
- `(is_active, latitude, longitude)` for candidate filtering.
- `retail_price` for price-aware selection.
- `opis_truckstop_id` should not be unique because the CSV contains duplicate IDs.

### LocationCache

Stores request-time geocoding results for start and destination strings.

Fields:

- `query`: normalized user-entered location string.
- `latitude`, `longitude`.
- `provider`: geocoding provider name.
- `raw_response`: optional JSON for debugging.
- `created_at`, `updated_at`.

Unique constraint:

- `query`.

## Import and Enrichment Workflow

Provide a Django management command:

```text
python manage.py import_fuel_prices fuel-prices-for-be-assessment.csv
```

Responsibilities:

1. Parse the CSV using Python's `csv` module.
2. Normalize whitespace, state codes, prices, and station names.
3. Upsert fuel stations by a stable row identity, preferably `source_row_hash` plus OPIS ID and station name.
4. Batch-geocode station addresses using Census batch geocoding.
5. Store coordinates and mark unmatched rows as inactive.
6. Produce an import summary:
   - total rows read
   - created count
   - updated count
   - active geocoded station count
   - unmatched or failed geocoding count
   - duplicate OPIS ID count

The importer should be repeatable. Running it again with the same CSV should not create duplicate rows.

## API

### Endpoint

```text
POST /api/routes/fuel-plan/
```

### Request

Coordinate input is preferred:

```json
{
  "start": {"lat": 30.2672, "lng": -97.7431},
  "destination": {"lat": 39.7392, "lng": -104.9903}
}
```

Address input is also supported:

```json
{
  "start": "Austin, TX",
  "destination": "Denver, CO"
}
```

Optional tuning:

```json
{
  "corridor_miles": 10,
  "max_range_miles": 500,
  "miles_per_gallon": 10
}
```

Validation rules:

- Start and destination are required.
- Coordinates must be valid latitude/longitude values.
- Address strings must resolve to locations inside the USA.
- `max_range_miles` defaults to 500 and should not exceed 500 for this assessment unless explicitly allowed.
- `miles_per_gallon` defaults to 10 and must be positive.
- `corridor_miles` defaults to 10 and should be capped, for example at 25, to avoid unrealistic detours.

### Success Response

```json
{
  "route": {
    "distance_miles": 928.4,
    "geometry": {
      "type": "LineString",
      "coordinates": []
    }
  },
  "fuel_plan": {
    "max_range_miles": 500,
    "miles_per_gallon": 10,
    "total_gallons": 92.84,
    "total_cost": 312.45,
    "currency": "USD",
    "stops": [
      {
        "station_id": 123,
        "name": "Example Travel Center",
        "address": "I-40, Exit 100",
        "city": "Example",
        "state": "TX",
        "lat": 32.1,
        "lng": -101.2,
        "price_per_gallon": 3.099,
        "route_mile": 421.6,
        "gallons": 42.16,
        "cost": 130.73
      }
    ]
  },
  "warnings": [],
  "metadata": {
    "fuel_data_version": "fuel-prices-for-be-assessment.csv",
    "active_station_count": 7420,
    "routing_provider": "osrm"
  }
}
```

### Error Responses

Unresolvable location:

```json
{
  "error": "location_not_found",
  "message": "Start or destination could not be resolved to a USA location."
}
```

No feasible fuel plan:

```json
{
  "error": "no_feasible_fuel_plan",
  "message": "A route was found, but the available fuel-price dataset does not contain enough reachable fuel stations to complete the trip within a 500-mile vehicle range."
}
```

Routing provider failure:

```json
{
  "error": "routing_unavailable",
  "message": "Route calculation is temporarily unavailable."
}
```

## Route and Stop Selection

### Candidate Filtering

After OSRM returns route geometry:

1. Convert route coordinates to a line representation.
2. Build a bounding box around the route expanded by `corridor_miles`.
3. Query active stations inside the bounding box.
4. Compute approximate distance from each station to the route.
5. Keep only stations within the route corridor.
6. Project each kept station onto the route to estimate `route_mile`.

For this assessment, Python geospatial calculations are acceptable. If dependencies are allowed, use Shapely for route projection and distance checks. If avoiding compiled dependencies is preferred, use a Haversine-based approximation over route segments.

### Optimization Strategy

Use a greedy fuel-cost algorithm over reachable stations ordered by route mile:

1. Add a virtual start point at mile 0 and a virtual destination at the final route mile.
2. At each stop, inspect stations reachable within the current range.
3. If a cheaper station is reachable ahead, buy only enough fuel to reach it.
4. If no cheaper station is reachable, fill enough to reach the cheapest viable downstream option or the destination.
5. If no station or destination is reachable within the range, return `no_feasible_fuel_plan`.

This is a small and maintainable approximation that fits the assessment. It produces cost-effective results without requiring a heavy graph optimizer.

Potential issue: because station detours are approximated by route projection, exact turn-by-turn detour distance is not included. This is acceptable if the corridor is kept small and the response includes route-mile metadata.

Starting fuel handling:

- Do not assume a free full tank at departure.
- Prefer an origin-area station, projected close to route mile 0, for the first purchase.
- If the first selected purchase occurs later on the route, include a warning that the plan assumes enough starting fuel to reach that first station.
- Keep this behavior deterministic and covered by tests so total spend does not change silently.

## Django Architecture

Use Django REST Framework with explicit service boundaries:

- `fuel.models`: `FuelStation`, `LocationCache`.
- `fuel.management.commands.import_fuel_prices`: CSV import and geocoding.
- `routing.serializers`: request and response serializers.
- `routing.views`: API view for `/api/routes/fuel-plan/`.
- `routing.services.geocoding`: start/destination geocoding and cache lookup.
- `routing.services.osrm`: OSRM route client.
- `routing.services.candidates`: route corridor station selection.
- `routing.services.optimizer`: fuel stop and spend calculation.

The view should validate input, call the orchestration service, and translate known domain exceptions into API responses. Business logic should not live in the view.

## Performance Plan

Request-time external calls:

- 0 calls if start/destination coordinates are provided and route is cached.
- 1 call if coordinates are provided and route is not cached.
- 2-3 calls if start/destination are strings and not in `LocationCache`.

Local performance:

- Keep active stations indexed.
- Use bounding-box filtering before route-distance calculations.
- Cache geocoded user locations.
- Optionally cache OSRM route responses by normalized coordinate pair.
- Avoid calling external services during station selection.

## Testing Plan

Importer tests:

- Parses the provided CSV header and sample rows.
- Handles duplicate OPIS IDs without failing.
- Marks ungeocoded stations inactive.
- Is idempotent when run twice.

Serializer tests:

- Accepts coordinate input.
- Accepts address string input.
- Rejects invalid coordinates.
- Rejects invalid tuning values.

Service tests:

- Candidate filtering returns only stations near a synthetic route.
- Optimizer handles a route under 500 miles.
- Optimizer handles a route requiring multiple stops.
- Optimizer returns no feasible plan when there is a gap over 500 miles.
- Cost calculation uses 10 MPG and station prices correctly.

API tests:

- Successful response includes route geometry, stops, total gallons, and total cost.
- Location-not-found maps to a clear error response.
- Routing-provider failure maps to a clear error response.
- No-feasible-plan maps to a clear error response.

Use mocked OSRM and geocoding clients in automated tests. Do not rely on live third-party APIs in test runs.

## Risks and Mitigations

- CSV lacks coordinates.
  - Mitigation: one-time batch geocoding and inactive status for unmatched rows.
- Free routing/geocoding services may rate-limit or fail.
  - Mitigation: cache request-time geocoding, keep route calls to one per request, and return explicit provider errors.
- Fuel optimization depends on starting tank assumptions.
  - Mitigation: document deterministic assumption and expose gallons/cost per stop.
- Route corridor matching is approximate.
  - Mitigation: keep corridor capped, return route-mile metadata, and avoid claiming exact detour optimization.
- Public OSRM demo service is not a production SLA.
  - Mitigation: isolate provider client behind a service interface so it can be swapped later.

## Acceptance Criteria

- A client can submit start and destination locations in the USA.
- The API returns route GeoJSON, total route distance, selected fuel stops, total gallons, and total fuel cost.
- The API respects the 500-mile range and 10 MPG assumptions.
- Fuel stops are chosen only from imported, active fuel-price data.
- Runtime route planning does not geocode the entire fuel dataset.
- Runtime route planning usually makes one external routing call when coordinates are provided.
- The importer can load and enrich the provided CSV repeatably.
- The API returns explicit errors for invalid locations, routing failures, and infeasible fuel plans.
