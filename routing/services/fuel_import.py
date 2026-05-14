import csv
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable


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


StationIdentity = tuple[str, str, str, str, str]


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def station_identity(row: FuelPriceRow) -> StationIdentity:
    return (
        row.opis_truckstop_id,
        row.address,
        row.city,
        row.state,
        row.rack_id,
    )


def station_identity_lookup(identity: StationIdentity) -> dict[str, str]:
    opis_truckstop_id, address, city, state, rack_id = identity
    return {
        "opis_truckstop_id": opis_truckstop_id,
        "address": address,
        "city": city,
        "state": state,
        "rack_id": rack_id,
    }


def row_hash(row: FuelPriceRow) -> str:
    row_values = [
        row.opis_truckstop_id,
        row.name,
        row.address,
        row.city,
        row.state,
        row.rack_id,
        str(row.retail_price),
    ]
    payload = json.dumps(row_values, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    from django.db import transaction
    from fuel.models import FuelStation

    rows = list(rows)
    total_rows = 0
    created = 0
    updated = 0
    duplicate_opis_ids = 0
    seen_opis_ids: set[str] = set()
    counted_updated_identities: set[StationIdentity] = set()

    with transaction.atomic():
        existing_identities = {
            identity
            for identity in {station_identity(row) for row in rows}
            if FuelStation.objects.filter(**station_identity_lookup(identity)).exists()
        }

        for row in rows:
            identity = station_identity(row)
            total_rows += 1
            if row.opis_truckstop_id in seen_opis_ids:
                duplicate_opis_ids += 1
            seen_opis_ids.add(row.opis_truckstop_id)

            _, was_created = FuelStation.objects.update_or_create(
                **station_identity_lookup(identity),
                defaults={
                    "name": row.name,
                    "retail_price": row.retail_price,
                    "source_row_hash": row_hash(row),
                },
            )

            if was_created:
                created += 1
            elif identity in existing_identities and identity not in counted_updated_identities:
                updated += 1
                counted_updated_identities.add(identity)

    return FuelImportSummary(
        total_rows=total_rows,
        created=created,
        updated=updated,
        duplicate_opis_ids=duplicate_opis_ids,
    )
