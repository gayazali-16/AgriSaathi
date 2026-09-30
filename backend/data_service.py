from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from backend.config import ROOT

DATA_DIR = ROOT / "backend" / "data" / "prepared"
GUIDANCE_FILE = ROOT / "backend" / "data" / "guidance.json"
DATASET_URL = "https://doi.org/10.5281/zenodo.21981601"


@lru_cache(maxsize=1)
def read_artifact(name: str) -> list[dict] | dict:
    path = DATA_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def guidance_cards() -> list[dict]:
    return json.loads(GUIDANCE_FILE.read_text(encoding="utf-8"))


def artifact_manifest() -> dict:
    return read_artifact("manifest.json")  # type: ignore[return-value]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def districts() -> list[dict]:
    return read_artifact("district_catalog.json")  # type: ignore[return-value]


def crop_entries(state: str, district: str) -> list[dict]:
    entries = read_artifact("crop_catalog.json")
    return [item for item in entries if item["state"] == state and item["district"] == district]  # type: ignore[union-attr]


def evidence_for_field(field: dict) -> list[dict]:
    matching = [
        item for item in read_artifact("historical_context.json")
        if item["state"] == field["state"] and item["district"] == field["district"]
    ]
    if field.get("season"):
        seasonal = [item for item in matching if item["season"].casefold() == field["season"].casefold()]
        if seasonal:
            matching = seasonal

    evidence = []
    for item in matching:
        identifier = f"dataset-history-{_slug(item['district'])}-{_slug(item['season'])}"
        evidence.append({
            "id": identifier,
            "type": "historical_dataset_summary",
            "label": f"Historical {item['season']} source values",
            "scope": f"{item['district']} district; historical source labels",
            "period": f"{item['period'][0]}-{item['period'][1]}",
            "spatial_precision": "district-level; not field-specific",
            "values": item["median_source_values"],
            "units": "not documented in the supplied CSV schema or README",
            "unit_status": "unverified",
            "unique_points": item["unique_climate_points_after_deduplication"],
            "artifact_version": artifact_manifest()["artifact_version"],
            "source_sha256": artifact_manifest()["source"]["sha256"],
            "warning": item["warning"],
            "source_title": "Agricultural dataset (see source README and DOI)",
            "source_url": DATASET_URL,
            "live": False,
        })
    return evidence


def _card_crops(card: dict) -> set[str]:
    values = card.get("crops") or [card.get("crop", "")]
    return {str(value).casefold() for value in values if value}


def _localized_card(card: dict, language: str) -> dict:
    translated = card.get("translations", {}).get(language, {})
    return {
        **{key: value for key, value in card.items() if key != "translations"},
        **translated,
    }


def _cards_for_field(field: dict, language: str = "en") -> list[dict]:
    crop = field["crop"].casefold()
    cards = [card for card in guidance_cards() if crop in _card_crops(card)]
    return [_localized_card(card, language) for card in cards]


def planning_for_field(field: dict, language: str = "en") -> dict:
    entries = crop_entries(field["state"], field["district"])
    historical_records = []
    for entry in entries:
        historical_records.append({
            "crop": entry["crop"],
            "historical_record_rows": entry["historical_record_rows"],
            "seasons": entry["seasons"],
            "year_range": entry["year_range"],
            "reason_key": "cropHistoryReason",
            "caveat_key": "cropHistoryCaveat",
            "evidence_ids": [f"crop-catalog-{_slug(field['district'])}-{_slug(entry['crop'])}"],
            "source_title": "Selected historical agriculture dataset",
            "source_url": DATASET_URL,
        })
    candidates = [
        candidate for candidate in historical_records
        if not field.get("season") or field["season"].casefold() in {s.casefold() for s in candidate["seasons"]}
    ]
    season_order = ["Kharif", "Rabi", "Zaid"]
    seasons_in_records = {season for candidate in historical_records for season in candidate["seasons"]}
    practices = [
        {**card, "evidence_ids": [card["id"]]}
        for card in _cards_for_field(field, language)
    ]
    return {
        "field_id": field["id"],
        "district": field["district"],
        "crop": field["crop"],
        "season": field["season"],
        "candidates": candidates,
        "practices": practices,
        "crop_cycle": {
            "previous_crop_options": sorted({candidate["crop"] for candidate in historical_records}),
            "historical_crop_records": historical_records,
            "seasons": [season for season in season_order if season in seasons_in_records]
                + sorted(seasons_in_records - set(season_order)),
            "sequence_data_available": False,
            "source_title": "Selected historical agriculture dataset",
            "source_url": DATASET_URL,
        },
        "source_policy": "Local record presence and cited practice context only; no yield or suitability prediction.",
    }


def practice_evidence(field: dict, language: str = "en") -> list[dict]:
    return [
        {
            "id": card["id"],
            "type": "curated_agronomy_reference",
            "label": card["title"],
            "topic": card["topic"],
            "scope": card["evidence_scope"],
            "why": card["why"],
            "practice": card["practice"],
            "source_title": card["source_title"],
            "source_url": card["source_url"],
            "live": False,
        }
        for card in _cards_for_field(field, language)
    ]


SOIL_FILE = ROOT / "backend" / "data" / "soil_observations.json"
SATELLITE_FILE = ROOT / "backend" / "data" / "satellite_observations.json"
PUBLIC_DIR = ROOT / "backend" / "data" / "public"


def public_reference(district: str, source: str) -> dict | None:
    # Only configured district slugs; never accept a caller-supplied path.
    slug = {"Nalgonda": "nalgonda", "Khammam": "khammam", "Krishna": "krishna"}.get(district)
    if not slug or source not in {"soil", "satellite", "climate"}:
        return None
    path = PUBLIC_DIR / slug / f"{source}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def climate_evidence(field: dict) -> dict | None:
    record = public_reference(field["district"], "climate")
    return {**record, "scope": record["spatial_scope"]} if record else None


@lru_cache(maxsize=1)
def soil_observations() -> list[dict]:
    if not SOIL_FILE.is_file():
        return []
    return json.loads(SOIL_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def satellite_observations() -> list[dict]:
    if not SATELLITE_FILE.is_file():
        return []
    return json.loads(SATELLITE_FILE.read_text(encoding="utf-8"))


def soil_observation_for_district(district: str) -> dict:
    verified = public_reference(district, "soil")
    if verified:
        return verified
    obs = next((item for item in soil_observations() if item["district"].casefold() == district.casefold()), None)
    if obs is None:
        return {
            "status": "unavailable",
            "reason": f"No plot-level soil test or district benchmark is connected for {district}.",
            "data_type": "missing",
            "live": False,
        }
    return obs


def satellite_observation_for_district(district: str) -> dict:
    verified = public_reference(district, "satellite")
    if verified:
        return verified
    obs = next((item for item in satellite_observations() if item["district"].casefold() == district.casefold()), None)
    if obs is None:
        return {
            "status": "unavailable",
            "reason": f"No dated satellite export is connected for {district}.",
            "data_type": "missing",
            "live": False,
        }
    return obs


def soil_evidence(field: dict) -> dict | None:
    obs = soil_observation_for_district(field["district"])
    if obs.get("status") != "available":
        return None
    return {
        "id": obs["id"],
        "type": "modelled_soil_estimate" if obs.get("data_type") == "modelled_soil_estimate" else "recorded_soil_observation",
        "label": f"District Soil Benchmark ({obs['soil_class']})",
        "scope": obs["spatial_scope"],
        "observed_at": obs["observed_at"],
        "soil_class": obs.get("soil_class"),
        "report_id": obs.get("report_id"),
        "geographic_bounds": obs.get("geographic_bounds"),
        "processing_method": obs.get("processing_method"),
        "verification_status": obs.get("verification_status", "unverified_demo_fixture"),
        "provenance_notes": obs.get("provenance_notes"),
        "values": obs["metrics"],
        "prediction_interval_90_percent": obs.get("prediction_interval_90_percent"),
        "warning": obs["warning"],
        "source_title": obs["source_title"],
        "source_url": obs["source_url"],
        "live": False,
    }


def satellite_evidence(field: dict) -> dict | None:
    obs = satellite_observation_for_district(field["district"])
    if obs.get("status") != "available":
        return None
    return {
        "id": obs["id"],
        "type": "recorded_satellite_observation",
        "label": f"Satellite Vegetation Index ({obs['sensor']})",
        "scope": obs["spatial_scope"],
        "observed_at": obs["observed_at"],
        "sensor": obs.get("sensor"),
        "scene_id": obs.get("scene_id"),
        "geographic_bounds": obs.get("geographic_bounds"),
        "processing_method": obs.get("processing_method"),
        "verification_status": obs.get("verification_status", "unverified_demo_fixture"),
        "provenance_notes": obs.get("provenance_notes"),
        "values": obs["metrics"],
        "observation_vs_inference": obs["observation_vs_inference"],
        "warning": obs["warning"],
        "source_title": obs["source_title"],
        "source_url": obs["source_url"],
        "live": False,
    }
