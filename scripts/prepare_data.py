#!/usr/bin/env python3
"""Prepare small, auditable artifacts from the supplied agriculture CSV.

The full CSV is streamed and never copied into this repository. Only verified
district/crop presence and deduplicated historical climate context are emitted.
Yield, production, soil-nutrient and fertilizer aggregates are intentionally
excluded from all output used by the application.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "backend" / "data" / "prepared"
EXPECTED = {
    ("Telangana", "Nalgonda"),
    ("Telangana", "Khammam"),
    ("Andhra Pradesh", "Krishna"),
}
TARGET_CROPS = {"rice", "maize"}
NUMERIC_FIELDS = {
    "Temperature": "unit_not_explicitly_documented",
    "Humidity": "unit_not_explicitly_documented",
    "Rainfall": "unit_not_explicitly_documented",
}
REQUIRED_HEADERS = {
    "Year", "Season", "Temperature", "Humidity", "Rainfall", "State",
    "District", "Crop",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value == value and abs(value) != float("inf") else None


def canonical_state_district(state: str, district: str) -> tuple[str, str] | None:
    normalized = (state.strip().casefold(), district.strip().casefold())
    return next(
        ((expected_state, expected_district)
         for expected_state, expected_district in EXPECTED
         if normalized == (expected_state.casefold(), expected_district.casefold())),
        None,
    )


def prepare(source: Path, output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(f"Dataset CSV not found: {source}")

    district_rows: Counter[tuple[str, str]] = Counter()
    crop_rows: Counter[tuple[str, str, str]] = Counter()
    crop_seasons: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    crop_years: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    # Weather values can be broadcast once per crop row. Deduplicate by
    # (year, season, climate tuple) before summarizing the selected crop rows.
    climate_points: dict[tuple[str, str], set[tuple[int, str, float | None, float | None, float | None]]] = defaultdict(set)
    climate_missing: Counter[tuple[str, str]] = Counter()
    years_by_district: dict[tuple[str, str], list[int]] = defaultdict(list)
    source_rows = 0
    selected_rows = 0
    malformed_year = 0

    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_HEADERS - headers)
        if missing:
            raise ValueError(f"Unexpected dataset schema; missing columns: {missing}")

        for row in reader:
            source_rows += 1
            canonical = canonical_state_district(row.get("State", ""), row.get("District", ""))
            if canonical is None:
                continue
            district_rows[canonical] += 1
            try:
                year = int(row.get("Year", ""))
            except (TypeError, ValueError):
                malformed_year += 1
                continue
            years_by_district[canonical].append(year)

            crop = (row.get("Crop") or "").strip()
            normalized_crop = crop.casefold()
            if normalized_crop not in TARGET_CROPS:
                continue

            selected_rows += 1
            crop_key = (*canonical, normalized_crop)
            crop_rows[crop_key] += 1
            season = (row.get("Season") or "Unknown").strip()
            crop_seasons[crop_key].add(season)
            crop_years[crop_key].append(year)

            climate_key = (*canonical,)
            temperature = number(row.get("Temperature"))
            humidity = number(row.get("Humidity"))
            rainfall = number(row.get("Rainfall"))
            if temperature is None or humidity is None or rainfall is None:
                climate_missing[canonical] += 1
            climate_points[canonical].add((year, season, temperature, humidity, rainfall))

    districts: list[dict[str, Any]] = []
    crop_catalog: list[dict[str, Any]] = []
    historical: list[dict[str, Any]] = []

    for state, district in sorted(EXPECTED):
        key = (state, district)
        years = years_by_district.get(key, [])
        present_crops = []
        for crop in sorted(TARGET_CROPS):
            crop_key = (state, district, crop)
            count = crop_rows[crop_key]
            if count == 0:
                continue
            display_name = crop.title()
            present_crops.append(display_name)
            crop_year_values = crop_years[crop_key]
            crop_catalog.append({
                "state": state,
                "district": district,
                "crop": display_name,
                "historical_record_rows": count,
                "seasons": sorted(crop_seasons[crop_key]),
                "year_range": [min(crop_year_values), max(crop_year_values)],
                "interpretation": "Historical dataset presence only; not a suitability score or current recommendation.",
            })
        districts.append({
            "state": state,
            "district": district,
            "historical_rows_all_crops": district_rows[key],
            "year_range": [min(years), max(years)] if years else None,
            "supported_crops": present_crops,
            "boundary_vintage": "Historical labels in source; current district boundaries not verified.",
        })

        points = sorted(
            climate_points.get(key, set()),
            key=lambda item: tuple(
                float("-inf") if value is None else value
                for value in (item[0], item[1], item[2], item[3], item[4])
            ),
        )
        climate_by_season: dict[str, list[tuple[int, float | None, float | None, float | None]]] = defaultdict(list)
        for year, season, temp, humidity, rain in points:
            climate_by_season[season].append((year, temp, humidity, rain))
        for season, observations in sorted(climate_by_season.items()):
            temperature_values = [item[1] for item in observations if item[1] is not None]
            humidity_values = [item[2] for item in observations if item[2] is not None]
            rainfall_values = [item[3] for item in observations if item[3] is not None]
            historical.append({
                "state": state,
                "district": district,
                "season": season,
                "period": [min(item[0] for item in observations), max(item[0] for item in observations)],
                "unique_climate_points_after_deduplication": len(observations),
                "median_source_values": {
                    "temperature": round(statistics.median(temperature_values), 2) if temperature_values else None,
                    "humidity": round(statistics.median(humidity_values), 2) if humidity_values else None,
                    "rainfall": round(statistics.median(rainfall_values), 2) if rainfall_values else None,
                },
                "range": {
                    "temperature_source_values": [round(min(temperature_values), 2), round(max(temperature_values), 2)] if temperature_values else None,
                    "humidity_source_values": [round(min(humidity_values), 2), round(max(humidity_values), 2)] if humidity_values else None,
                    "rainfall_source_values": [round(min(rainfall_values), 2), round(max(rainfall_values), 2)] if rainfall_values else None,
                },
                "missing_climate_row_count": climate_missing[key],
                "evidence_type": "historical_dataset_summary",
                "warning": "Historical district context deduplicated from selected crop rows; it is not a current forecast or a field measurement.",
            })

    source_hash = sha256_file(source)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = {
        "artifact_version": "1.0.0",
        "generated_at_utc": generated_at,
        "source": {
            "filename": source.name,
            "sha256": source_hash,
            "license": "MIT; original notice is retained in DATASET-LICENSE.",
            "citation": "See docs/sources/crop-dataset-README.md and docs/sources/crop-dataset-references.pdf.",
        },
        "filters": {
            "regions": [{"state": state, "district": district} for state, district in sorted(EXPECTED)],
            "core_crops": ["Maize", "Rice"],
            "district_rows_retain_all_crops_for_coverage_count_only": True,
        },
        "counts": {
            "source_data_rows": source_rows,
            "selected_district_rows_all_crops": sum(district_rows.values()),
            "selected_district_rice_maize_rows": selected_rows,
            "malformed_year_in_selected_district_rows": malformed_year,
        },
        "field_units": NUMERIC_FIELDS,
        "excluded_source_fields": [
            "soil type used as farm-specific diagnosis", "nitrogen/phosphate/potash consumption or shares",
            "total consumption", "area", "production", "average yield", "chemical/organic fertilizer prescriptions",
            "intercropping and crop rotation strings as confirmed field practice",
        ],
        "limitations": [
            "Original data spans historical years and labels; administrative boundaries are not verified against current districts.",
            "Rows are dataset records, not farm counts or guaranteed independent climate observations.",
            "Repeated joins/broadcast values are suspected; historical climate rows are deduplicated by year, season, and value tuple.",
            "A crop's presence in the source does not prove present-day local suitability.",
            "Source-level missingness and row lineage are incomplete; invalid numeric values are omitted, not imputed.",
        ],
    }
    quality = {
        "source_rows": source_rows,
        "selected_district_rows": sum(district_rows.values()),
        "selected_rice_maize_rows": selected_rows,
        "districts": [
            {
                "state": item["state"], "district": item["district"],
                "all_crop_rows": item["historical_rows_all_crops"],
                "year_range": item["year_range"],
                "rice_maize_rows": sum(crop_rows[(item["state"], item["district"], crop)] for crop in TARGET_CROPS),
                "deduplicated_climate_points": len(climate_points[(item["state"], item["district"])]),
                "rows_missing_one_or_more_climate_fields": climate_missing[(item["state"], item["district"])],
            }
            for item in districts
        ],
        "decisions": [
            "Historical temperature, atmospheric relative humidity, and rainfall are summarized only as district context.",
            "Rows duplicated across selected crops are collapsed when year, season, and all three climate values match.",
            "No suspect production, yield, NPK, area, irrigation, or prescription values are emitted to the runtime artifact.",
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "district_catalog.json": districts,
        "crop_catalog.json": crop_catalog,
        "historical_context.json": historical,
        "quality_report.json": quality,
        "manifest.json": manifest,
    }
    for filename, payload in artifacts.items():
        (output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return {"artifacts": sorted(artifacts), "quality": quality, "manifest": manifest}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path,
        default=Path(__import__("os").environ.get(
            "DATA_SOURCE_PATH",
            str(REPO_ROOT.parent / "crop-research-data" / "crops_dataset.csv"),
        )),
        help="Path to the supplied crops_dataset.csv (or set DATA_SOURCE_PATH).",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    result = prepare(args.source, args.output)
    print(json.dumps({"artifacts": result["artifacts"], "quality": result["quality"]}, indent=2))


if __name__ == "__main__":
    main()
