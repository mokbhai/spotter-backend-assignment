#!/bin/sh
set -eu

python manage.py migrate --noinput

if [ "${SPOTTER_IMPORT_FUEL_PRICES:-false}" = "true" ]; then
  python manage.py import_fuel_prices fuel-prices-for-be-assessment.csv --skip-geocoding
fi

exec "$@"
