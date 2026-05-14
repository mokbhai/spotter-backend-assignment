from django.core.management.base import BaseCommand, CommandError

from fuel.models import FuelStation
from routing.exceptions import RoutingProviderError
from routing.services.fuel_import import import_fuel_price_rows, parse_fuel_price_csv
from routing.services.geocoding import (
    CensusBatchStationGeocoder,
    apply_station_geocoding_results,
)


class Command(BaseCommand):
    help = "Import fuel station prices from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument(
            "--skip-geocoding",
            action="store_true",
            help="Load fuel prices without geocoding stations.",
        )

    def handle(self, *args, **options):
        rows = parse_fuel_price_csv(options["csv_path"])
        summary = import_fuel_price_rows(rows)

        self.stdout.write(
            "Imported fuel prices: "
            f"total={summary.total_rows} "
            f"created={summary.created} "
            f"updated={summary.updated} "
            f"duplicate_opis_ids={summary.duplicate_opis_ids}"
        )

        if options["skip_geocoding"]:
            self.stdout.write("Skipped station geocoding.")
            return

        stations = list(
            FuelStation.objects.filter(
                geocoding_status=FuelStation.GeocodingStatus.PENDING
            )
        )
        if not stations:
            self.stdout.write("No pending stations to geocode.")
            return

        try:
            results = CensusBatchStationGeocoder().geocode_stations(stations)
        except RoutingProviderError as exc:
            raise CommandError(f"Station batch geocoding failed: {exc}") from exc

        geocoding_summary = apply_station_geocoding_results(results)
        self.stdout.write(
            "Station geocoding summary: "
            f"matched={geocoding_summary.matched} "
            f"unmatched={geocoding_summary.unmatched} "
            f"failed={geocoding_summary.failed}"
        )
