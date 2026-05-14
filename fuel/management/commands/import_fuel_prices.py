from django.core.management.base import BaseCommand

from routing.services.fuel_import import import_fuel_price_rows, parse_fuel_price_csv


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

        self.stdout.write(
            "Station geocoding is not implemented yet. Re-run with --skip-geocoding."
        )
