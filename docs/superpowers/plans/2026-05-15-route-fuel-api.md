# Route Fuel Stop API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Django REST API that returns a USA route, cost-effective fuel stops from the provided CSV dataset, and estimated fuel spend.

**Complete Target:** A complete backend feature: CSV fuel station import/enrichment, local station cache, routing/geocoding service boundaries, fuel-stop optimizer, DRF endpoint, tests, and basic usage documentation.

**Architecture:** Use a small Django project with DRF. Keep HTTP concerns in views/serializers, business workflows in service modules, station data in models, and third-party API calls behind provider clients that can be mocked in tests.

**Tech Stack:** Python 3.14 local interpreter, Django 6.x, Django REST Framework 3.17+, requests, pytest, pytest-django, SQLite for local assessment storage.

**Spec Source:** `docs/superpowers/specs/2026-05-15-route-fuel-api-design.md`

**Phase:** single-plan

**Next Required Phase:** none

---

## Important Implementation Notes

- The current directory is not a git repository. Commit steps are included for normal workflow, but they must be skipped unless git is initialized.
- Keep tests independent of live OSRM and Census calls. Mock provider clients in tests.
- Accept coordinates as the fastest happy path. Address strings are supported through request-time geocoding and cache lookup.
- Do not make station coordinates required at database level. The importer must be able to preserve unmatched rows for diagnostics while marking them inactive.
- Do not assume OPIS truckstop IDs are unique; the CSV contains duplicates.
- Do not call the geocoder for every station during route requests. Station geocoding belongs only in the import command.
- Use dependency-light route corridor math instead of Shapely for this assessment.

## File Structure

Create this project layout:

```text
manage.py
requirements.txt
pytest.ini
README.md
spotter_backend/
  __init__.py
  settings.py
  urls.py
  wsgi.py
  asgi.py
fuel/
  __init__.py
  admin.py
  apps.py
  models.py
  migrations/
    __init__.py
  management/
    __init__.py
    commands/
      __init__.py
      import_fuel_prices.py
routing/
  __init__.py
  apps.py
  exceptions.py
  serializers.py
  urls.py
  views.py
  services/
    __init__.py
    candidates.py
    fuel_import.py
    geocoding.py
    geometry.py
    optimizer.py
    osrm.py
    planner.py
tests/
  __init__.py
  conftest.py
  test_api.py
  test_candidates.py
  test_fuel_import.py
  test_geocoding.py
  test_optimizer.py
  test_serializers.py
```

Responsibilities:

- `fuel.models`: persisted station and location cache records.
- `routing.services.fuel_import`: CSV parsing, normalization, row hashing, importer helper functions.
- `fuel.management.commands.import_fuel_prices`: CLI wrapper around importer helpers and Census batch geocoding.
- `routing.services.geocoding`: request-time location normalization, cache lookup, provider client.
- `routing.services.osrm`: OSRM route client and route response normalization.
- `routing.services.geometry`: distance, route projection, bounding-box utilities.
- `routing.services.candidates`: database filtering and route-corridor station projection.
- `routing.services.optimizer`: deterministic fuel purchase plan.
- `routing.services.planner`: orchestration for the API endpoint.
- `routing.serializers`: DRF request validation and response-facing primitives.
- `routing.views`: one API view that maps domain exceptions to HTTP responses.

---

### Task 1: Scaffold Django Project and Test Harness

**Files:**
- Create: `requirements.txt`
- Create: `manage.py`
- Create: `spotter_backend/__init__.py`
- Create: `spotter_backend/settings.py`
- Create: `spotter_backend/urls.py`
- Create: `spotter_backend/wsgi.py`
- Create: `spotter_backend/asgi.py`
- Create: `fuel/__init__.py`
- Create: `fuel/apps.py`
- Create: `fuel/admin.py`
- Create: `fuel/migrations/__init__.py`
- Create: `routing/__init__.py`
- Create: `routing/apps.py`
- Create: `routing/urls.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`

- [ ] **Step 1: Write the project smoke test**

Create `tests/test_api.py` with:

```python
def test_django_settings_load(settings):
    assert "rest_framework" in settings.INSTALLED_APPS
    assert "fuel" in settings.INSTALLED_APPS
    assert "routing" in settings.INSTALLED_APPS
```

- [ ] **Step 2: Add dependencies**

Create `requirements.txt`:

```text
Django>=6.0,<6.1
djangorestframework>=3.17,<4
requests>=2.32,<3
pytest>=8.0,<9
pytest-django>=4.9,<5
```

- [ ] **Step 3: Create the Django project files**

Create `manage.py`:

```python
#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "spotter_backend.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

Create `spotter_backend/settings.py`:

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "assessment-local-secret-key"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "fuel",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "spotter_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "spotter_backend.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}

OSRM_BASE_URL = "https://router.project-osrm.org"
CENSUS_GEOCODER_BASE_URL = "https://geocoding.geo.census.gov/geocoder"
DEFAULT_ROUTE_CORRIDOR_MILES = 10
MAX_ROUTE_CORRIDOR_MILES = 25
DEFAULT_MAX_RANGE_MILES = 500
DEFAULT_MILES_PER_GALLON = 10
```

Create `spotter_backend/urls.py`:

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/routes/", include("routing.urls")),
]
```

Create `spotter_backend/wsgi.py`:

```python
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "spotter_backend.settings")

application = get_wsgi_application()
```

Create `spotter_backend/asgi.py`:

```python
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "spotter_backend.settings")

application = get_asgi_application()
```

Create `fuel/apps.py`:

```python
from django.apps import AppConfig


class FuelConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fuel"
```

Create `routing/apps.py`:

```python
from django.apps import AppConfig


class RoutingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "routing"
```

Create `routing/urls.py`:

```python
from django.urls import path

urlpatterns = []
```

Create `pytest.ini`:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = spotter_backend.settings
python_files = tests.py test_*.py *_tests.py
```

Create `tests/conftest.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def _enable_db_access_for_all_tests(db):
    pass
```

- [ ] **Step 4: Run the smoke test**

Run:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest tests/test_api.py::test_django_settings_load -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

If git is initialized:

```bash
git add .
git commit -m "chore: scaffold django route planner"
```

---

### Task 2: Add Fuel Models and Migrations

**Files:**
- Create/Modify: `fuel/models.py`
- Modify: `fuel/admin.py`
- Generate: `fuel/migrations/0001_initial.py`
- Test: `tests/test_fuel_import.py`

- [ ] **Step 1: Write model tests**

Create `tests/test_fuel_import.py` with:

```python
from decimal import Decimal

from fuel.models import FuelStation, LocationCache


def test_fuel_station_allows_duplicate_opis_ids():
    FuelStation.objects.create(
        opis_truckstop_id="20",
        name="PILOT TRAVEL CENTER #1243",
        address="I-8, EXIT 119 & SR-85",
        city="Gila Bend",
        state="AZ",
        rack_id="930",
        retail_price=Decimal("3.899"),
        source_row_hash="hash-one",
        is_active=False,
    )
    FuelStation.objects.create(
        opis_truckstop_id="20",
        name="PILOT #1243",
        address="I-8, EXIT 119 & SR-85",
        city="Gila Bend",
        state="AZ",
        rack_id="930",
        retail_price=Decimal("3.899"),
        source_row_hash="hash-two",
        is_active=False,
    )

    assert FuelStation.objects.filter(opis_truckstop_id="20").count() == 2


def test_location_cache_query_is_unique():
    LocationCache.objects.create(query="austin, tx", latitude=30.2672, longitude=-97.7431)

    assert LocationCache.objects.get(query="austin, tx").latitude == Decimal("30.267200")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_fuel_import.py -v
```

Expected: FAIL because `fuel.models.FuelStation` and `LocationCache` are not defined.

- [ ] **Step 3: Implement models**

Create `fuel/models.py`:

```python
from django.db import models


class FuelStation(models.Model):
    class GeocodingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        MATCHED = "matched", "Matched"
        UNMATCHED = "unmatched", "Unmatched"
        FAILED = "failed", "Failed"

    opis_truckstop_id = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=8)
    rack_id = models.CharField(max_length=32)
    retail_price = models.DecimalField(max_digits=8, decimal_places=4)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geocoding_status = models.CharField(
        max_length=16,
        choices=GeocodingStatus.choices,
        default=GeocodingStatus.PENDING,
    )
    geocoding_score = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    source_row_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["state", "city"]),
            models.Index(fields=["is_active", "latitude", "longitude"]),
            models.Index(fields=["retail_price"]),
            models.Index(fields=["opis_truckstop_id"]),
        ]
        ordering = ["name", "city", "state"]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"


class LocationCache(models.Model):
    query = models.CharField(max_length=255, unique=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    provider = models.CharField(max_length=64, default="census")
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["query"]

    def __str__(self):
        return self.query
```

Create `fuel/admin.py`:

```python
from django.contrib import admin

from fuel.models import FuelStation, LocationCache


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "retail_price", "is_active", "geocoding_status")
    list_filter = ("state", "is_active", "geocoding_status")
    search_fields = ("name", "city", "state", "opis_truckstop_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(LocationCache)
class LocationCacheAdmin(admin.ModelAdmin):
    list_display = ("query", "latitude", "longitude", "provider", "updated_at")
    search_fields = ("query",)
    readonly_fields = ("created_at", "updated_at")
```

- [ ] **Step 4: Generate and apply migrations**

Run:

```bash
python manage.py makemigrations fuel
python manage.py migrate
```

Expected: migration creates `FuelStation` and `LocationCache`.

- [ ] **Step 5: Run model tests**

Run:

```bash
pytest tests/test_fuel_import.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

If git is initialized:

```bash
git add fuel tests/test_fuel_import.py
git commit -m "feat: add fuel station models"
```

---

### Task 3: Implement CSV Parsing and Idempotent Import Helpers

**Files:**
- Create: `routing/services/fuel_import.py`
- Modify: `tests/test_fuel_import.py`

- [ ] **Step 1: Add failing parser tests**

Append to `tests/test_fuel_import.py`:

```python
import csv
from pathlib import Path

import pytest

from routing.services.fuel_import import FuelPriceRow, import_fuel_price_rows, parse_fuel_price_csv


def test_parse_fuel_price_csv_normalizes_rows(tmp_path):
    path = tmp_path / "fuel.csv"
    path.write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "79,DELAWARE TRUCK PLAZA,US-13 & US-40,New Castle                              ,DE,243,3.249\n",
        encoding="utf-8",
    )

    rows = list(parse_fuel_price_csv(path))

    assert rows == [
        FuelPriceRow(
            opis_truckstop_id="79",
            name="DELAWARE TRUCK PLAZA",
            address="US-13 & US-40",
            city="New Castle",
            state="DE",
            rack_id="243",
            retail_price=Decimal("3.249"),
        )
    ]


@pytest.mark.django_db
def test_import_fuel_price_rows_is_idempotent():
    row = FuelPriceRow(
        opis_truckstop_id="79",
        name="DELAWARE TRUCK PLAZA",
        address="US-13 & US-40",
        city="New Castle",
        state="DE",
        rack_id="243",
        retail_price=Decimal("3.249"),
    )

    first = import_fuel_price_rows([row])
    second = import_fuel_price_rows([row])

    assert first.created == 1
    assert first.updated == 0
    assert second.created == 0
    assert second.updated == 1
    assert FuelStation.objects.count() == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_fuel_import.py -v
```

Expected: FAIL because `routing.services.fuel_import` does not exist.

- [ ] **Step 3: Implement import helpers**

Create `routing/services/fuel_import.py`:

```python
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from fuel.models import FuelStation


@dataclass(frozen=True)
class FuelPriceRow:
    opis_truckstop_id: str
    name: str
    address: str
    city: str
    state: str
    rack_id: str
    retail_price: Decimal


@dataclass(frozen=True)
class FuelImportSummary:
    total_rows: int
    created: int
    updated: int
    duplicate_opis_ids: int


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def row_hash(row: FuelPriceRow) -> str:
    raw = "|".join(
        [
            row.opis_truckstop_id,
            row.name,
            row.address,
            row.city,
            row.state,
            row.rack_id,
            str(row.retail_price),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_fuel_price_csv(path: str | Path) -> Iterable[FuelPriceRow]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for record in reader:
            yield FuelPriceRow(
                opis_truckstop_id=normalize_text(record["OPIS Truckstop ID"]),
                name=normalize_text(record["Truckstop Name"]),
                address=normalize_text(record["Address"]),
                city=normalize_text(record["City"]),
                state=normalize_text(record["State"]).upper(),
                rack_id=normalize_text(record["Rack ID"]),
                retail_price=Decimal(normalize_text(record["Retail Price"])),
            )


def import_fuel_price_rows(rows: Iterable[FuelPriceRow]) -> FuelImportSummary:
    created = 0
    updated = 0
    total = 0
    seen_opis_ids: set[str] = set()
    duplicate_opis_ids = 0

    for row in rows:
        total += 1
        if row.opis_truckstop_id in seen_opis_ids:
            duplicate_opis_ids += 1
        seen_opis_ids.add(row.opis_truckstop_id)

        _, was_created = FuelStation.objects.update_or_create(
            source_row_hash=row_hash(row),
            defaults={
                "opis_truckstop_id": row.opis_truckstop_id,
                "name": row.name,
                "address": row.address,
                "city": row.city,
                "state": row.state,
                "rack_id": row.rack_id,
                "retail_price": row.retail_price,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return FuelImportSummary(
        total_rows=total,
        created=created,
        updated=updated,
        duplicate_opis_ids=duplicate_opis_ids,
    )
```

- [ ] **Step 4: Run parser/import tests**

Run:

```bash
pytest tests/test_fuel_import.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

If git is initialized:

```bash
git add routing/services/fuel_import.py tests/test_fuel_import.py
git commit -m "feat: parse fuel price csv"
```

---

### Task 4: Add Geocoding Service and Station Import Command

**Files:**
- Create: `routing/exceptions.py`
- Create: `routing/services/geocoding.py`
- Create: `fuel/management/__init__.py`
- Create: `fuel/management/commands/__init__.py`
- Create: `fuel/management/commands/import_fuel_prices.py`
- Create/Modify: `tests/test_geocoding.py`
- Modify: `tests/test_fuel_import.py`

- [ ] **Step 1: Write geocoding cache tests**

Create `tests/test_geocoding.py`:

```python
from decimal import Decimal

import pytest

from fuel.models import LocationCache
from routing.services.geocoding import GeocodedLocation, resolve_location


class FakeGeocoder:
    def geocode_one(self, query):
        return GeocodedLocation(
            query=query,
            latitude=Decimal("30.267200"),
            longitude=Decimal("-97.743100"),
            provider="fake",
            raw_response={"ok": True},
        )


@pytest.mark.django_db
def test_resolve_location_uses_cache_before_provider():
    LocationCache.objects.create(
        query="austin, tx",
        latitude=Decimal("30.267200"),
        longitude=Decimal("-97.743100"),
        provider="cached",
    )

    location = resolve_location("Austin, TX", provider=FakeGeocoder())

    assert location.provider == "cached"
    assert location.latitude == Decimal("30.267200")


@pytest.mark.django_db
def test_resolve_location_stores_provider_result():
    location = resolve_location("Austin, TX", provider=FakeGeocoder())

    assert location.provider == "fake"
    assert LocationCache.objects.get(query="austin, tx").longitude == Decimal("-97.743100")
```

- [ ] **Step 2: Write management command test**

Append to `tests/test_fuel_import.py`:

```python
from django.core.management import call_command


@pytest.mark.django_db
def test_import_command_loads_csv_without_live_geocoding(tmp_path, monkeypatch):
    path = tmp_path / "fuel.csv"
    path.write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "79,DELAWARE TRUCK PLAZA,US-13 & US-40,New Castle,DE,243,3.249\n",
        encoding="utf-8",
    )

    call_command("import_fuel_prices", str(path), "--skip-geocoding")

    station = FuelStation.objects.get(opis_truckstop_id="79")
    assert station.is_active is False
    assert station.geocoding_status == FuelStation.GeocodingStatus.PENDING
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
pytest tests/test_geocoding.py tests/test_fuel_import.py -v
```

Expected: FAIL because geocoding service and command do not exist.

- [ ] **Step 4: Implement geocoding service**

Create `routing/services/geocoding.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import requests
from django.conf import settings

from fuel.models import LocationCache
from routing.exceptions import LocationNotFoundError


@dataclass(frozen=True)
class GeocodedLocation:
    query: str
    latitude: Decimal
    longitude: Decimal
    provider: str
    raw_response: dict


class SingleGeocoder(Protocol):
    def geocode_one(self, query: str) -> GeocodedLocation | None:
        ...


def normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


class CensusGeocoder:
    def __init__(self, base_url: str | None = None, timeout: int = 10):
        self.base_url = base_url or settings.CENSUS_GEOCODER_BASE_URL
        self.timeout = timeout

    def geocode_one(self, query: str) -> GeocodedLocation | None:
        response = requests.get(
            f"{self.base_url}/locations/onelineaddress",
            params={
                "address": query,
                "benchmark": "Public_AR_Current",
                "format": "json",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        matches = payload.get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        coordinates = matches[0]["coordinates"]
        return GeocodedLocation(
            query=query,
            latitude=Decimal(str(coordinates["y"])),
            longitude=Decimal(str(coordinates["x"])),
            provider="census",
            raw_response=matches[0],
        )


def resolve_location(query: str, provider: SingleGeocoder | None = None) -> GeocodedLocation:
    normalized = normalize_query(query)
    cached = LocationCache.objects.filter(query=normalized).first()
    if cached:
        return GeocodedLocation(
            query=query,
            latitude=cached.latitude,
            longitude=cached.longitude,
            provider=cached.provider,
            raw_response=cached.raw_response,
        )

    provider = provider or CensusGeocoder()
    location = provider.geocode_one(query)
    if location is None:
        raise LocationNotFoundError("Location could not be resolved.")

    LocationCache.objects.update_or_create(
        query=normalized,
        defaults={
            "latitude": location.latitude,
            "longitude": location.longitude,
            "provider": location.provider,
            "raw_response": location.raw_response,
        },
    )
    return location
```

Create `routing/exceptions.py`:

```python
class RoutingError(Exception):
    pass


class LocationNotFoundError(RoutingError):
    pass


class RoutingProviderError(RoutingError):
    pass


class NoFeasibleFuelPlanError(RoutingError):
    pass
```

- [ ] **Step 5: Implement management command**

Create `fuel/management/commands/import_fuel_prices.py`:

```python
from django.core.management.base import BaseCommand

from routing.services.fuel_import import import_fuel_price_rows, parse_fuel_price_csv


class Command(BaseCommand):
    help = "Import fuel prices from the assessment CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument(
            "--skip-geocoding",
            action="store_true",
            help="Load station rows without calling external geocoding.",
        )

    def handle(self, *args, **options):
        rows = parse_fuel_price_csv(options["csv_path"])
        summary = import_fuel_price_rows(rows)
        self.stdout.write(
            self.style.SUCCESS(
                "Imported fuel rows: "
                f"total={summary.total_rows}, created={summary.created}, "
                f"updated={summary.updated}, duplicate_opis_ids={summary.duplicate_opis_ids}"
            )
        )
        if options["skip_geocoding"]:
            self.stdout.write("Skipped station geocoding.")
```

- [ ] **Step 6: Run tests**

Run:

```bash
pytest tests/test_geocoding.py tests/test_fuel_import.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

If git is initialized:

```bash
git add fuel/management routing/exceptions.py routing/services/geocoding.py tests
git commit -m "feat: add geocoding cache and import command"
```

---

### Task 5: Implement Census Batch Station Geocoding

**Files:**
- Modify: `routing/services/geocoding.py`
- Modify: `fuel/management/commands/import_fuel_prices.py`
- Modify: `tests/test_geocoding.py`
- Modify: `tests/test_fuel_import.py`

- [ ] **Step 1: Add Census batch parser tests**

Append to `tests/test_geocoding.py`:

```python
from fuel.models import FuelStation
from routing.services.geocoding import (
    StationGeocodeResult,
    apply_station_geocoding_results,
    parse_census_batch_response,
)


def test_parse_census_batch_response_extracts_coordinates():
    response_text = (
        '"123","I-35, Austin, TX","Match","Exact","I-35, Austin, TX","-97.743100,30.267200","1","L"\n'
        '"124","Missing","No_Match","","","","",""\n'
    )

    results = parse_census_batch_response(response_text)

    assert results["123"] == StationGeocodeResult(
        station_id=123,
        matched=True,
        latitude=Decimal("30.267200"),
        longitude=Decimal("-97.743100"),
        score=None,
    )
    assert results["124"].matched is False


def test_apply_station_geocoding_results_marks_matched_and_unmatched():
    matched = FuelStation.objects.create(
        opis_truckstop_id="1",
        name="Matched",
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.0000"),
        source_row_hash="batch-matched",
    )
    unmatched = FuelStation.objects.create(
        opis_truckstop_id="2",
        name="Unmatched",
        address="Bad",
        city="Nowhere",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.0000"),
        source_row_hash="batch-unmatched",
    )

    summary = apply_station_geocoding_results(
        {
            str(matched.id): StationGeocodeResult(
                station_id=matched.id,
                matched=True,
                latitude=Decimal("30.267200"),
                longitude=Decimal("-97.743100"),
                score=None,
            ),
            str(unmatched.id): StationGeocodeResult(
                station_id=unmatched.id,
                matched=False,
                latitude=None,
                longitude=None,
                score=None,
            ),
        }
    )

    matched.refresh_from_db()
    unmatched.refresh_from_db()
    assert summary.matched == 1
    assert summary.unmatched == 1
    assert matched.is_active is True
    assert matched.geocoding_status == FuelStation.GeocodingStatus.MATCHED
    assert unmatched.is_active is False
    assert unmatched.geocoding_status == FuelStation.GeocodingStatus.UNMATCHED
```

- [ ] **Step 2: Add command test for mocked batch geocoding**

Append to `tests/test_fuel_import.py`:

```python
from routing.services.geocoding import StationGeocodeResult


class FakeBatchGeocoder:
    def geocode_stations(self, stations):
        return {
            str(station.id): StationGeocodeResult(
                station_id=station.id,
                matched=True,
                latitude=Decimal("39.680000"),
                longitude=Decimal("-75.750000"),
                score=None,
            )
            for station in stations
        }


@pytest.mark.django_db
def test_import_command_can_apply_batch_geocoding(tmp_path, monkeypatch):
    path = tmp_path / "fuel.csv"
    path.write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "79,DELAWARE TRUCK PLAZA,US-13 & US-40,New Castle,DE,243,3.249\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "fuel.management.commands.import_fuel_prices.CensusBatchStationGeocoder",
        lambda: FakeBatchGeocoder(),
    )

    call_command("import_fuel_prices", str(path))

    station = FuelStation.objects.get(opis_truckstop_id="79")
    assert station.is_active is True
    assert station.latitude == Decimal("39.680000")
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
pytest tests/test_geocoding.py tests/test_fuel_import.py -v
```

Expected: FAIL because batch station geocoding helpers do not exist yet.

- [ ] **Step 4: Implement Census batch helpers**

Extend `routing/services/geocoding.py`:

```python
import csv
import io
from dataclasses import dataclass

from fuel.models import FuelStation


@dataclass(frozen=True)
class StationGeocodeResult:
    station_id: int
    matched: bool
    latitude: Decimal | None
    longitude: Decimal | None
    score: Decimal | None = None


@dataclass(frozen=True)
class StationGeocodingSummary:
    matched: int
    unmatched: int
    failed: int


def build_census_batch_input(stations) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    for station in stations:
        writer.writerow([station.id, station.address, station.city, station.state, ""])
    return output.getvalue()


def parse_census_batch_response(response_text: str) -> dict[str, StationGeocodeResult]:
    results = {}
    reader = csv.reader(io.StringIO(response_text))
    for row in reader:
        if not row:
            continue
        station_id = row[0]
        match_status = row[2] if len(row) > 2 else ""
        coordinates = row[5] if len(row) > 5 else ""
        if match_status == "Match" and coordinates:
            longitude, latitude = [Decimal(part.strip()) for part in coordinates.split(",", maxsplit=1)]
            results[station_id] = StationGeocodeResult(
                station_id=int(station_id),
                matched=True,
                latitude=latitude,
                longitude=longitude,
                score=None,
            )
        else:
            results[station_id] = StationGeocodeResult(
                station_id=int(station_id),
                matched=False,
                latitude=None,
                longitude=None,
                score=None,
            )
    return results


class CensusBatchStationGeocoder:
    def __init__(self, base_url: str | None = None, timeout: int = 60):
        self.base_url = base_url or settings.CENSUS_GEOCODER_BASE_URL
        self.timeout = timeout

    def geocode_stations(self, stations) -> dict[str, StationGeocodeResult]:
        batch_input = build_census_batch_input(stations)
        response = requests.post(
            f"{self.base_url}/locations/addressbatch",
            data={"benchmark": "Public_AR_Current"},
            files={"addressFile": ("stations.csv", batch_input, "text/csv")},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return parse_census_batch_response(response.text)


def apply_station_geocoding_results(results: dict[str, StationGeocodeResult]) -> StationGeocodingSummary:
    matched = 0
    unmatched = 0
    failed = 0

    for station_id, result in results.items():
        try:
            station = FuelStation.objects.get(id=int(station_id))
        except FuelStation.DoesNotExist:
            failed += 1
            continue

        if result.matched:
            station.latitude = result.latitude
            station.longitude = result.longitude
            station.geocoding_score = result.score
            station.geocoding_status = FuelStation.GeocodingStatus.MATCHED
            station.is_active = True
            matched += 1
        else:
            station.latitude = None
            station.longitude = None
            station.geocoding_status = FuelStation.GeocodingStatus.UNMATCHED
            station.is_active = False
            unmatched += 1
        station.save(
            update_fields=[
                "latitude",
                "longitude",
                "geocoding_score",
                "geocoding_status",
                "is_active",
                "updated_at",
            ]
        )

    return StationGeocodingSummary(matched=matched, unmatched=unmatched, failed=failed)
```

- [ ] **Step 5: Wire batch geocoding into the import command**

Update `fuel/management/commands/import_fuel_prices.py`:

```python
from django.core.management.base import BaseCommand

from fuel.models import FuelStation
from routing.services.fuel_import import import_fuel_price_rows, parse_fuel_price_csv
from routing.services.geocoding import CensusBatchStationGeocoder, apply_station_geocoding_results


class Command(BaseCommand):
    help = "Import fuel prices from the assessment CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument(
            "--skip-geocoding",
            action="store_true",
            help="Load station rows without calling external geocoding.",
        )

    def handle(self, *args, **options):
        rows = parse_fuel_price_csv(options["csv_path"])
        summary = import_fuel_price_rows(rows)
        self.stdout.write(
            self.style.SUCCESS(
                "Imported fuel rows: "
                f"total={summary.total_rows}, created={summary.created}, "
                f"updated={summary.updated}, duplicate_opis_ids={summary.duplicate_opis_ids}"
            )
        )

        if options["skip_geocoding"]:
            self.stdout.write("Skipped station geocoding.")
            return

        stations = list(FuelStation.objects.filter(geocoding_status=FuelStation.GeocodingStatus.PENDING))
        if not stations:
            self.stdout.write("No pending stations to geocode.")
            return

        results = CensusBatchStationGeocoder().geocode_stations(stations)
        geocoding_summary = apply_station_geocoding_results(results)
        self.stdout.write(
            self.style.SUCCESS(
                "Geocoded stations: "
                f"matched={geocoding_summary.matched}, "
                f"unmatched={geocoding_summary.unmatched}, "
                f"failed={geocoding_summary.failed}"
            )
        )
```

- [ ] **Step 6: Run batch geocoding tests**

Run:

```bash
pytest tests/test_geocoding.py tests/test_fuel_import.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

If git is initialized:

```bash
git add routing/services/geocoding.py fuel/management/commands/import_fuel_prices.py tests
git commit -m "feat: enrich fuel stations with census batch geocoding"
```

---

### Task 6: Add OSRM Client

**Files:**
- Create: `routing/services/osrm.py`
- Create/Modify: `tests/test_api.py`

- [ ] **Step 1: Add OSRM client tests**

Append to `tests/test_api.py`:

```python
from decimal import Decimal

import pytest

from routing.exceptions import RoutingProviderError
from routing.services.osrm import OSRMClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("bad status")

    def json(self):
        return self._payload


def test_osrm_client_normalizes_route(monkeypatch):
    def fake_get(url, params, timeout):
        assert "route/v1/driving/-97.7431,30.2672;-104.9903,39.7392" in url
        assert params["geometries"] == "geojson"
        return FakeResponse(
            payload={
                "code": "Ok",
                "routes": [
                    {
                        "distance": 1609.344,
                        "geometry": {"type": "LineString", "coordinates": [[-97.7, 30.2], [-104.9, 39.7]]},
                    }
                ],
            }
        )

    monkeypatch.setattr("routing.services.osrm.requests.get", fake_get)

    route = OSRMClient().route(
        start_lat=Decimal("30.2672"),
        start_lng=Decimal("-97.7431"),
        dest_lat=Decimal("39.7392"),
        dest_lng=Decimal("-104.9903"),
    )

    assert route.distance_miles == pytest.approx(1.0, rel=0.001)
    assert route.geometry["type"] == "LineString"


def test_osrm_client_raises_provider_error(monkeypatch):
    def fake_get(url, params, timeout):
        return FakeResponse(payload={"code": "NoRoute", "routes": []})

    monkeypatch.setattr("routing.services.osrm.requests.get", fake_get)

    with pytest.raises(RoutingProviderError):
        OSRMClient().route(Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"))
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_api.py -v
```

Expected: FAIL because `routing.services.osrm` does not exist.

- [ ] **Step 3: Implement OSRM client**

Create `routing/services/osrm.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import requests
from django.conf import settings

from routing.exceptions import RoutingProviderError

METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class Route:
    distance_miles: float
    geometry: dict


class OSRMClient:
    def __init__(self, base_url: str | None = None, timeout: int = 15):
        self.base_url = (base_url or settings.OSRM_BASE_URL).rstrip("/")
        self.timeout = timeout

    def route(
        self,
        start_lat: Decimal,
        start_lng: Decimal,
        dest_lat: Decimal,
        dest_lng: Decimal,
    ) -> Route:
        coordinates = f"{start_lng},{start_lat};{dest_lng},{dest_lat}"
        try:
            response = requests.get(
                f"{self.base_url}/route/v1/driving/{coordinates}",
                params={"overview": "full", "geometries": "geojson", "steps": "false"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise RoutingProviderError("Route calculation failed.") from exc

        routes = payload.get("routes", [])
        if payload.get("code") != "Ok" or not routes:
            raise RoutingProviderError("Route calculation failed.")

        route = routes[0]
        return Route(
            distance_miles=float(route["distance"]) / METERS_PER_MILE,
            geometry=route["geometry"],
        )
```

- [ ] **Step 4: Run OSRM tests**

Run:

```bash
pytest tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

If git is initialized:

```bash
git add routing/services/osrm.py tests/test_api.py
git commit -m "feat: add osrm route client"
```

---

### Task 7: Add Request Serializer

**Files:**
- Create: `routing/serializers.py`
- Modify: `tests/test_serializers.py`

- [ ] **Step 1: Write serializer tests**

Create `tests/test_serializers.py`:

```python
from routing.serializers import FuelPlanRequestSerializer


def test_fuel_plan_serializer_accepts_coordinates():
    serializer = FuelPlanRequestSerializer(
        data={
            "start": {"lat": 30.2672, "lng": -97.7431},
            "destination": {"lat": 39.7392, "lng": -104.9903},
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["max_range_miles"] == 500
    assert serializer.validated_data["miles_per_gallon"] == 10
    assert serializer.validated_data["corridor_miles"] == 10


def test_fuel_plan_serializer_accepts_strings():
    serializer = FuelPlanRequestSerializer(data={"start": "Austin, TX", "destination": "Denver, CO"})

    assert serializer.is_valid(), serializer.errors


def test_fuel_plan_serializer_rejects_invalid_corridor():
    serializer = FuelPlanRequestSerializer(
        data={
            "start": "Austin, TX",
            "destination": "Denver, CO",
            "corridor_miles": 99,
        }
    )

    assert not serializer.is_valid()
    assert "corridor_miles" in serializer.errors


def test_fuel_plan_serializer_rejects_coordinates_outside_usa_bounds():
    serializer = FuelPlanRequestSerializer(
        data={
            "start": {"lat": 48.8566, "lng": 2.3522},
            "destination": {"lat": 39.7392, "lng": -104.9903},
        }
    )

    assert not serializer.is_valid()
    assert "start" in serializer.errors
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_serializers.py -v
```

Expected: FAIL because `FuelPlanRequestSerializer` does not exist.

- [ ] **Step 3: Implement serializer**

Create `routing/serializers.py`:

```python
from rest_framework import serializers


class CoordinateSerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)

    def validate(self, attrs):
        lat = attrs["lat"]
        lng = attrs["lng"]
        if not (18 <= lat <= 72 and -170 <= lng <= -66):
            raise serializers.ValidationError("Coordinates must be within broad USA bounds.")
        return attrs


class LocationField(serializers.Field):
    def to_internal_value(self, data):
        if isinstance(data, str) and data.strip():
            return data.strip()
        if isinstance(data, dict):
            serializer = CoordinateSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            return serializer.validated_data
        raise serializers.ValidationError("Expected a non-empty string or {lat, lng} object.")

    def to_representation(self, value):
        return value


class FuelPlanRequestSerializer(serializers.Serializer):
    start = LocationField()
    destination = LocationField()
    corridor_miles = serializers.IntegerField(required=False, default=10, min_value=1, max_value=25)
    max_range_miles = serializers.IntegerField(required=False, default=500, min_value=1, max_value=500)
    miles_per_gallon = serializers.DecimalField(
        required=False,
        default=10,
        max_digits=6,
        decimal_places=2,
        min_value=1,
    )
```

- [ ] **Step 4: Run serializer tests**

Run:

```bash
pytest tests/test_serializers.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

If git is initialized:

```bash
git add routing/serializers.py tests/test_serializers.py
git commit -m "feat: validate fuel plan requests"
```

---

### Task 8: Add Geometry and Candidate Selection

**Files:**
- Create: `routing/services/geometry.py`
- Create: `routing/services/candidates.py`
- Create: `tests/test_candidates.py`

- [ ] **Step 1: Write geometry/candidate tests**

Create `tests/test_candidates.py`:

```python
from decimal import Decimal

import pytest

from fuel.models import FuelStation
from routing.services.candidates import find_candidate_stations
from routing.services.geometry import haversine_miles


def test_haversine_miles_is_reasonable():
    distance = haversine_miles(30.2672, -97.7431, 30.2672, -98.7431)

    assert distance == pytest.approx(59.7, rel=0.05)


@pytest.mark.django_db
def test_find_candidate_stations_filters_by_route_corridor():
    near = FuelStation.objects.create(
        opis_truckstop_id="1",
        name="Near",
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.0000"),
        latitude=Decimal("30.267200"),
        longitude=Decimal("-97.743100"),
        geocoding_status=FuelStation.GeocodingStatus.MATCHED,
        source_row_hash="near",
        is_active=True,
    )
    FuelStation.objects.create(
        opis_truckstop_id="2",
        name="Far",
        address="Somewhere",
        city="Dallas",
        state="TX",
        rack_id="1",
        retail_price=Decimal("2.5000"),
        latitude=Decimal("32.776700"),
        longitude=Decimal("-96.797000"),
        geocoding_status=FuelStation.GeocodingStatus.MATCHED,
        source_row_hash="far",
        is_active=True,
    )
    route_geometry = {
        "type": "LineString",
        "coordinates": [[-97.7431, 30.2672], [-97.7431, 30.5]],
    }

    candidates = find_candidate_stations(route_geometry, corridor_miles=10)

    assert [candidate.station.id for candidate in candidates] == [near.id]
    assert candidates[0].route_mile == pytest.approx(0, abs=1)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_candidates.py -v
```

Expected: FAIL because geometry and candidate services do not exist.

- [ ] **Step 3: Implement geometry helpers**

Create `routing/services/geometry.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_MILES = 3958.7613


@dataclass(frozen=True)
class ProjectedPoint:
    distance_to_route_miles: float
    route_mile: float


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def route_points(geometry: dict) -> list[tuple[float, float]]:
    return [(float(lat), float(lng)) for lng, lat in geometry["coordinates"]]


def expanded_bounding_box(points: list[tuple[float, float]], miles: float) -> tuple[float, float, float, float]:
    lats = [point[0] for point in points]
    lngs = [point[1] for point in points]
    lat_delta = miles / 69.0
    avg_lat = sum(lats) / len(lats)
    lng_delta = miles / max(1.0, 69.0 * math.cos(math.radians(avg_lat)))
    return min(lats) - lat_delta, max(lats) + lat_delta, min(lngs) - lng_delta, max(lngs) + lng_delta


def cumulative_route_miles(points: list[tuple[float, float]]) -> list[float]:
    totals = [0.0]
    for start, end in zip(points, points[1:]):
        totals.append(totals[-1] + haversine_miles(start[0], start[1], end[0], end[1]))
    return totals


def project_point_to_route(lat: float, lng: float, points: list[tuple[float, float]]) -> ProjectedPoint:
    totals = cumulative_route_miles(points)
    best_distance = float("inf")
    best_route_mile = 0.0

    for index, (start, end) in enumerate(zip(points, points[1:])):
        mid_lat = (start[0] + end[0]) / 2
        miles_per_lat = 69.0
        miles_per_lng = max(1.0, 69.0 * math.cos(math.radians(mid_lat)))

        sx, sy = start[1] * miles_per_lng, start[0] * miles_per_lat
        ex, ey = end[1] * miles_per_lng, end[0] * miles_per_lat
        px, py = lng * miles_per_lng, lat * miles_per_lat

        dx = ex - sx
        dy = ey - sy
        segment_length_sq = dx * dx + dy * dy
        if segment_length_sq == 0:
            t = 0
        else:
            t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / segment_length_sq))

        projected_x = sx + t * dx
        projected_y = sy + t * dy
        distance = math.hypot(px - projected_x, py - projected_y)
        segment_miles = totals[index + 1] - totals[index]
        route_mile = totals[index] + (segment_miles * t)

        if distance < best_distance:
            best_distance = distance
            best_route_mile = route_mile

    return ProjectedPoint(distance_to_route_miles=best_distance, route_mile=best_route_mile)
```

- [ ] **Step 4: Implement candidate selection**

Create `routing/services/candidates.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fuel.models import FuelStation
from routing.services.geometry import expanded_bounding_box, project_point_to_route, route_points


@dataclass(frozen=True)
class CandidateStation:
    station: FuelStation
    route_mile: float
    distance_to_route_miles: float


def find_candidate_stations(route_geometry: dict, corridor_miles: int) -> list[CandidateStation]:
    points = route_points(route_geometry)
    min_lat, max_lat, min_lng, max_lng = expanded_bounding_box(points, corridor_miles)

    stations = FuelStation.objects.filter(
        is_active=True,
        latitude__isnull=False,
        longitude__isnull=False,
        latitude__gte=Decimal(str(min_lat)),
        latitude__lte=Decimal(str(max_lat)),
        longitude__gte=Decimal(str(min_lng)),
        longitude__lte=Decimal(str(max_lng)),
    )

    candidates = []
    for station in stations:
        projection = project_point_to_route(float(station.latitude), float(station.longitude), points)
        if projection.distance_to_route_miles <= corridor_miles:
            candidates.append(
                CandidateStation(
                    station=station,
                    route_mile=projection.route_mile,
                    distance_to_route_miles=projection.distance_to_route_miles,
                )
            )

    return sorted(candidates, key=lambda candidate: candidate.route_mile)
```

- [ ] **Step 5: Run candidate tests**

Run:

```bash
pytest tests/test_candidates.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

If git is initialized:

```bash
git add routing/services/geometry.py routing/services/candidates.py tests/test_candidates.py
git commit -m "feat: select fuel stations near route"
```

---

### Task 9: Implement Fuel Optimizer

**Files:**
- Create: `routing/services/optimizer.py`
- Create: `tests/test_optimizer.py`

- [ ] **Step 1: Write optimizer tests**

Create `tests/test_optimizer.py`:

```python
from dataclasses import dataclass
from decimal import Decimal

import pytest

from routing.exceptions import NoFeasibleFuelPlanError
from routing.services.optimizer import OptimizerStation, build_fuel_plan


def test_optimizer_handles_trip_under_range_with_origin_station():
    station = OptimizerStation(
        station_id=1,
        name="Origin Fuel",
        address="I-35",
        city="Austin",
        state="TX",
        lat=Decimal("30.000000"),
        lng=Decimal("-97.000000"),
        price_per_gallon=Decimal("3.0000"),
        route_mile=0,
    )

    plan = build_fuel_plan(
        stations=[station],
        route_distance_miles=100,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
    )

    assert plan.total_gallons == Decimal("10.00")
    assert plan.total_cost == Decimal("30.00")
    assert plan.stops[0].gallons == Decimal("10.00")


def test_optimizer_buys_less_when_cheaper_station_is_reachable():
    expensive = OptimizerStation(1, "Expensive", "A", "A", "TX", Decimal("1"), Decimal("1"), Decimal("5.0000"), 0)
    cheap = OptimizerStation(2, "Cheap", "B", "B", "TX", Decimal("1"), Decimal("1"), Decimal("3.0000"), 100)

    plan = build_fuel_plan(
        stations=[expensive, cheap],
        route_distance_miles=300,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
    )

    assert plan.stops[0].gallons == Decimal("10.00")
    assert plan.stops[1].gallons == Decimal("20.00")
    assert plan.total_cost == Decimal("110.00")


def test_optimizer_raises_when_gap_exceeds_range():
    station = OptimizerStation(1, "Only", "A", "A", "TX", Decimal("1"), Decimal("1"), Decimal("3.0000"), 0)

    with pytest.raises(NoFeasibleFuelPlanError):
        build_fuel_plan(
            stations=[station],
            route_distance_miles=700,
            max_range_miles=500,
            miles_per_gallon=Decimal("10"),
        )
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_optimizer.py -v
```

Expected: FAIL because optimizer does not exist.

- [ ] **Step 3: Implement optimizer**

Create `routing/services/optimizer.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from routing.exceptions import NoFeasibleFuelPlanError


@dataclass(frozen=True)
class OptimizerStation:
    station_id: int
    name: str
    address: str
    city: str
    state: str
    lat: Decimal
    lng: Decimal
    price_per_gallon: Decimal
    route_mile: float


@dataclass(frozen=True)
class FuelStop:
    station_id: int
    name: str
    address: str
    city: str
    state: str
    lat: Decimal
    lng: Decimal
    price_per_gallon: Decimal
    route_mile: float
    gallons: Decimal
    cost: Decimal


@dataclass(frozen=True)
class FuelPlan:
    total_gallons: Decimal
    total_cost: Decimal
    stops: list[FuelStop]
    warnings: list[str]


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def gallons(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_fuel_plan(
    stations: list[OptimizerStation],
    route_distance_miles: float,
    max_range_miles: int,
    miles_per_gallon: Decimal,
) -> FuelPlan:
    ordered = sorted(stations, key=lambda station: station.route_mile)
    if not ordered:
        raise NoFeasibleFuelPlanError("No fuel stations are available near this route.")

    if ordered[0].route_mile > max_range_miles:
        raise NoFeasibleFuelPlanError("No reachable first fuel station is available.")

    warnings = []
    if ordered[0].route_mile > 5:
        warnings.append("Plan assumes enough starting fuel to reach the first selected station.")

    stops: list[FuelStop] = []
    current_index = 0
    current_mile = ordered[0].route_mile

    while current_mile < route_distance_miles:
        current_station = ordered[current_index]
        remaining_miles = route_distance_miles - current_mile
        reachable = [
            (index, station)
            for index, station in enumerate(ordered[current_index + 1 :], start=current_index + 1)
            if 0 < station.route_mile - current_mile <= max_range_miles
        ]
        cheaper = [
            (index, station)
            for index, station in reachable
            if station.price_per_gallon < current_station.price_per_gallon
        ]

        if cheaper:
            next_index, next_station = cheaper[0]
            target_mile = next_station.route_mile
        elif remaining_miles <= max_range_miles:
            target_mile = route_distance_miles
            next_index = None
        elif reachable:
            next_index, next_station = min(reachable, key=lambda item: item[1].price_per_gallon)
            target_mile = next_station.route_mile
        else:
            raise NoFeasibleFuelPlanError("No reachable downstream fuel station is available.")

        miles_to_cover = Decimal(str(target_mile - current_mile))
        stop_gallons = gallons(miles_to_cover / miles_per_gallon)
        stop_cost = money(stop_gallons * current_station.price_per_gallon)

        if stop_gallons > 0:
            stops.append(
                FuelStop(
                    station_id=current_station.station_id,
                    name=current_station.name,
                    address=current_station.address,
                    city=current_station.city,
                    state=current_station.state,
                    lat=current_station.lat,
                    lng=current_station.lng,
                    price_per_gallon=current_station.price_per_gallon,
                    route_mile=current_station.route_mile,
                    gallons=stop_gallons,
                    cost=stop_cost,
                )
            )

        if next_index is None:
            break

        current_index = next_index
        current_mile = ordered[current_index].route_mile

    return FuelPlan(
        total_gallons=gallons(sum((stop.gallons for stop in stops), Decimal("0"))),
        total_cost=money(sum((stop.cost for stop in stops), Decimal("0"))),
        stops=stops,
        warnings=warnings,
    )
```

- [ ] **Step 4: Run optimizer tests**

Run:

```bash
pytest tests/test_optimizer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

If git is initialized:

```bash
git add routing/services/optimizer.py tests/test_optimizer.py
git commit -m "feat: optimize route fuel purchases"
```

---

### Task 10: Add Planner Orchestration Service

**Files:**
- Create: `routing/services/planner.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write planner test**

Append to `tests/test_api.py`:

```python
from decimal import Decimal

from fuel.models import FuelStation
from routing.services.osrm import Route
from routing.services.planner import build_route_fuel_plan


class FakeRouter:
    def route(self, start_lat, start_lng, dest_lat, dest_lng):
        return Route(
            distance_miles=100,
            geometry={"type": "LineString", "coordinates": [[-97.7431, 30.2672], [-97.7431, 30.5000]]},
        )


def test_planner_returns_route_and_fuel_plan():
    FuelStation.objects.create(
        opis_truckstop_id="1",
        name="Origin Fuel",
        address="I-35",
        city="Austin",
        state="TX",
        rack_id="1",
        retail_price=Decimal("3.0000"),
        latitude=Decimal("30.267200"),
        longitude=Decimal("-97.743100"),
        geocoding_status=FuelStation.GeocodingStatus.MATCHED,
        source_row_hash="planner-origin",
        is_active=True,
    )

    result = build_route_fuel_plan(
        start={"lat": Decimal("30.2672"), "lng": Decimal("-97.7431")},
        destination={"lat": Decimal("30.5000"), "lng": Decimal("-97.7431")},
        corridor_miles=10,
        max_range_miles=500,
        miles_per_gallon=Decimal("10"),
        router=FakeRouter(),
    )

    assert result["route"]["distance_miles"] == 100
    assert result["fuel_plan"]["total_cost"] == Decimal("30.00")
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_api.py::test_planner_returns_route_and_fuel_plan -v
```

Expected: FAIL because planner does not exist.

- [ ] **Step 3: Implement planner**

Create `routing/services/planner.py`:

```python
from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from routing.services.candidates import find_candidate_stations
from routing.services.geocoding import resolve_location
from routing.services.optimizer import OptimizerStation, build_fuel_plan
from routing.services.osrm import OSRMClient, Route


class Router(Protocol):
    def route(self, start_lat: Decimal, start_lng: Decimal, dest_lat: Decimal, dest_lng: Decimal) -> Route:
        ...


def resolve_input_location(value):
    if isinstance(value, dict):
        return value["lat"], value["lng"]
    location = resolve_location(value)
    return location.latitude, location.longitude


def build_route_fuel_plan(
    *,
    start,
    destination,
    corridor_miles: int,
    max_range_miles: int,
    miles_per_gallon: Decimal,
    router: Router | None = None,
) -> dict:
    start_lat, start_lng = resolve_input_location(start)
    dest_lat, dest_lng = resolve_input_location(destination)

    router = router or OSRMClient()
    route = router.route(start_lat, start_lng, dest_lat, dest_lng)
    candidates = find_candidate_stations(route.geometry, corridor_miles)
    optimizer_stations = [
        OptimizerStation(
            station_id=candidate.station.id,
            name=candidate.station.name,
            address=candidate.station.address,
            city=candidate.station.city,
            state=candidate.station.state,
            lat=candidate.station.latitude,
            lng=candidate.station.longitude,
            price_per_gallon=candidate.station.retail_price,
            route_mile=candidate.route_mile,
        )
        for candidate in candidates
    ]
    fuel_plan = build_fuel_plan(
        stations=optimizer_stations,
        route_distance_miles=route.distance_miles,
        max_range_miles=max_range_miles,
        miles_per_gallon=miles_per_gallon,
    )

    return {
        "route": {
            "distance_miles": round(route.distance_miles, 2),
            "geometry": route.geometry,
        },
        "fuel_plan": {
            "max_range_miles": max_range_miles,
            "miles_per_gallon": miles_per_gallon,
            "total_gallons": fuel_plan.total_gallons,
            "total_cost": fuel_plan.total_cost,
            "currency": "USD",
            "stops": [
                {
                    "station_id": stop.station_id,
                    "name": stop.name,
                    "address": stop.address,
                    "city": stop.city,
                    "state": stop.state,
                    "lat": stop.lat,
                    "lng": stop.lng,
                    "price_per_gallon": stop.price_per_gallon,
                    "route_mile": round(stop.route_mile, 2),
                    "gallons": stop.gallons,
                    "cost": stop.cost,
                }
                for stop in fuel_plan.stops
            ],
        },
        "warnings": fuel_plan.warnings,
        "metadata": {
            "routing_provider": "osrm",
        },
    }
```

- [ ] **Step 4: Run planner test**

Run:

```bash
pytest tests/test_api.py::test_planner_returns_route_and_fuel_plan -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

If git is initialized:

```bash
git add routing/services/planner.py tests/test_api.py
git commit -m "feat: orchestrate route fuel planning"
```

---

### Task 11: Add DRF API View

**Files:**
- Modify: `routing/views.py`
- Modify: `routing/urls.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write API endpoint tests**

Append to `tests/test_api.py`:

```python
from rest_framework.test import APIClient

from routing.exceptions import NoFeasibleFuelPlanError


def test_fuel_plan_endpoint_returns_success(monkeypatch):
    def fake_build_route_fuel_plan(**kwargs):
        return {
            "route": {"distance_miles": 100, "geometry": {"type": "LineString", "coordinates": []}},
            "fuel_plan": {
                "max_range_miles": 500,
                "miles_per_gallon": Decimal("10.00"),
                "total_gallons": Decimal("10.00"),
                "total_cost": Decimal("30.00"),
                "currency": "USD",
                "stops": [],
            },
            "warnings": [],
            "metadata": {"routing_provider": "osrm"},
        }

    monkeypatch.setattr("routing.views.build_route_fuel_plan", fake_build_route_fuel_plan)

    response = APIClient().post(
        "/api/routes/fuel-plan/",
        {"start": {"lat": 30.2672, "lng": -97.7431}, "destination": {"lat": 39.7392, "lng": -104.9903}},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["fuel_plan"]["total_cost"] == 30.0


def test_fuel_plan_endpoint_maps_no_feasible_plan(monkeypatch):
    def fake_build_route_fuel_plan(**kwargs):
        raise NoFeasibleFuelPlanError("No plan")

    monkeypatch.setattr("routing.views.build_route_fuel_plan", fake_build_route_fuel_plan)

    response = APIClient().post(
        "/api/routes/fuel-plan/",
        {"start": "Austin, TX", "destination": "Denver, CO"},
        format="json",
    )

    assert response.status_code == 422
    assert response.json()["error"] == "no_feasible_fuel_plan"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_api.py::test_fuel_plan_endpoint_returns_success tests/test_api.py::test_fuel_plan_endpoint_maps_no_feasible_plan -v
```

Expected: FAIL because view and URL are not implemented.

- [ ] **Step 3: Implement view**

Create `routing/views.py`:

```python
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from routing.exceptions import LocationNotFoundError, NoFeasibleFuelPlanError, RoutingProviderError
from routing.serializers import FuelPlanRequestSerializer
from routing.services.planner import build_route_fuel_plan


class FuelPlanView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = FuelPlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = build_route_fuel_plan(**serializer.validated_data)
        except LocationNotFoundError:
            return Response(
                {
                    "error": "location_not_found",
                    "message": "Start or destination could not be resolved to a USA location.",
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except NoFeasibleFuelPlanError:
            return Response(
                {
                    "error": "no_feasible_fuel_plan",
                    "message": (
                        "A route was found, but the available fuel-price dataset does not contain enough "
                        "reachable fuel stations to complete the trip within a 500-mile vehicle range."
                    ),
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except RoutingProviderError:
            return Response(
                {
                    "error": "routing_unavailable",
                    "message": "Route calculation is temporarily unavailable.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(result)
```

Update `routing/urls.py`:

```python
from django.urls import path

from routing.views import FuelPlanView

urlpatterns = [
    path("fuel-plan/", FuelPlanView.as_view(), name="fuel-plan"),
]
```

- [ ] **Step 4: Run API tests**

Run:

```bash
pytest tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

If git is initialized:

```bash
git add routing/views.py routing/urls.py tests/test_api.py
git commit -m "feat: expose route fuel plan api"
```

---

### Task 12: Add README and Full Verification

**Files:**
- Create/Modify: `README.md`

- [ ] **Step 1: Write usage docs**

Create `README.md`:

```markdown
# Spotter Backend Assignment

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
```

## Import Fuel Prices

```bash
python manage.py import_fuel_prices fuel-prices-for-be-assessment.csv
```

Use `--skip-geocoding` only when you want to load rows without calling the Census batch geocoder.

## Run API

```bash
python manage.py runserver
```

## Request

```bash
curl -X POST http://127.0.0.1:8000/api/routes/fuel-plan/ \
  -H 'Content-Type: application/json' \
  -d '{
    "start": {"lat": 30.2672, "lng": -97.7431},
    "destination": {"lat": 39.7392, "lng": -104.9903}
  }'
```

## Test

```bash
pytest
```
```

- [ ] **Step 2: Run all tests**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 3: Run Django checks**

Run:

```bash
python manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 4: Run importer against provided CSV without live geocoding**

Run:

```bash
python manage.py import_fuel_prices fuel-prices-for-be-assessment.csv --skip-geocoding
```

Expected: command prints `total=8151` and does not crash on duplicate OPIS IDs.

- [ ] **Step 5: Optional live station geocoding smoke test**

Only run this when external network access is acceptable:

```bash
python manage.py import_fuel_prices fuel-prices-for-be-assessment.csv
```

Expected: command prints `total=8151` and then a geocoding summary with matched/unmatched counts.

- [ ] **Step 6: Optional live API smoke test**

Only after some stations have coordinates in the database, run:

```bash
python manage.py runserver
```

Then:

```bash
curl -X POST http://127.0.0.1:8000/api/routes/fuel-plan/ \
  -H 'Content-Type: application/json' \
  -d '{"start":{"lat":30.2672,"lng":-97.7431},"destination":{"lat":39.7392,"lng":-104.9903}}'
```

Expected: either a successful fuel plan or a clear `no_feasible_fuel_plan` response if no active geocoded stations exist.

- [ ] **Step 7: Commit**

If git is initialized:

```bash
git add README.md
git commit -m "docs: add route fuel api usage"
```

---

## Final Verification Checklist

- [ ] `pytest -v` passes.
- [ ] `python manage.py check` passes.
- [ ] `python manage.py migrate` applies cleanly on a fresh SQLite database.
- [ ] `python manage.py import_fuel_prices fuel-prices-for-be-assessment.csv --skip-geocoding` reads all 8,151 rows.
- [ ] `python manage.py import_fuel_prices fuel-prices-for-be-assessment.csv` can batch-geocode stations when network access is available.
- [ ] The API accepts coordinate input.
- [ ] The API accepts address string input with mocked geocoder tests.
- [ ] No automated test depends on live OSRM or Census APIs.
- [ ] Runtime route planning does not geocode the station dataset.
- [ ] The response exposes route GeoJSON, fuel stops, total gallons, total cost, warnings, and metadata.
