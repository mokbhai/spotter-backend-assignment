#!/bin/sh
set -eu

is_enabled() {
  case "${1:-}" in
    1 | true | TRUE | yes | YES | on | ON) return 0 ;;
    *) return 1 ;;
  esac
}

if is_enabled "${SPOTTER_RUN_MIGRATIONS:-true}"; then
  python manage.py migrate --noinput
fi

if is_enabled "${SPOTTER_IMPORT_FUEL_PRICES:-true}"; then
  import_args=""
  if ! is_enabled "${SPOTTER_IMPORT_FUEL_PRICES_GEOCODE:-false}"; then
    import_args="--skip-geocoding"
  fi

  # shellcheck disable=SC2086
  python manage.py import_fuel_prices fuel-prices-for-be-assessment.csv $import_args
fi

exec "$@"
