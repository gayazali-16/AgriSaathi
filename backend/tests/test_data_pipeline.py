import json
from pathlib import Path

from scripts.prepare_data import prepare
from backend.database import DEMO_FIELDS
from backend.data_service import planning_for_field


HEADERS = "Year,Season,Temperature,Humidity,Rainfall,State,District,Crop,Total_Production_Tonnes,NITROGEN CONSUMPTION (tons)\n"


def test_prepare_deduplicates_climate_points_and_keeps_suspect_fields_out(tmp_path: Path):
    source = tmp_path / "tiny.csv"
    source.write_text(
        HEADERS
        + "2001,Kharif,28.0,70,120,Telangana,Nalgonda,Rice,999999,888\n"
        + "2001,Kharif,28.0,70,120,Telangana,Nalgonda,Maize,999999,888\n"
        + "2002,Rabi,25.0,65,80,Telangana,Nalgonda,Rice,111111,777\n",
        encoding="utf-8",
    )
    output = tmp_path / "prepared"
    result = prepare(source, output)

    assert result["quality"]["selected_district_rows"] == 3
    assert result["quality"]["selected_rice_maize_rows"] == 3
    context = json.loads((output / "historical_context.json").read_text(encoding="utf-8"))
    kharif = next(item for item in context if item["district"] == "Nalgonda" and item["season"] == "Kharif")
    assert kharif["unique_climate_points_after_deduplication"] == 1
    assert kharif["median_source_values"]["temperature"] == 28.0
    serialized_runtime = (output / "historical_context.json").read_text(encoding="utf-8")
    assert "Total_Production_Tonnes" not in serialized_runtime
    assert "NITROGEN CONSUMPTION" not in serialized_runtime
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["field_units"].values()) == {"unit_not_explicitly_documented"}


def test_committed_subset_records_measured_source_coverage():
    artifact_dir = Path(__file__).resolve().parents[1] / "data" / "prepared"
    quality = json.loads((artifact_dir / "quality_report.json").read_text(encoding="utf-8"))
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert quality["source_rows"] == 1_194_806
    assert quality["selected_district_rows"] == 10_416
    assert quality["selected_rice_maize_rows"] == 672
    assert manifest["artifact_version"] == "1.0.0"
    assert len(manifest["source"]["sha256"]) == 64


def test_crop_practice_cards_are_relevant_and_localized():
    rice = next(item for item in DEMO_FIELDS if item["district"] == "Krishna")
    maize = next(item for item in DEMO_FIELDS if item["crop"] == "Maize")

    rice_plan = planning_for_field(rice, "te")
    maize_plan = planning_for_field(maize, "hi")

    rice_topics = {item["topic"] for item in rice_plan["practices"]}
    maize_topics = {item["topic"] for item in maize_plan["practices"]}
    assert {"water_management", "nutrient_management", "crop_rotation", "integrated_pest_management"} <= rice_topics
    assert {"nutrient_management", "crop_rotation", "intercropping", "integrated_pest_management"} <= maize_topics
    assert all(item["title"] and item["practice"] and item["why"] and item["evidence_scope"] for item in rice_plan["practices"])
    assert all("translations" not in item for item in rice_plan["practices"])
    assert any("మట్టి" in item["practice"] or "పంట" in item["practice"] for item in rice_plan["practices"])
    assert any("मिट्टी" in item["practice"] or "फसल" in item["practice"] for item in maize_plan["practices"])


def test_crop_cycle_uses_historical_crop_seasons_without_claiming_rotation_sequences():
    rice_field = next(item for item in DEMO_FIELDS if item["district"] == "Nalgonda" and item["crop"] == "Rice")
    plan = planning_for_field(rice_field)
    cycle = plan["crop_cycle"]

    assert cycle["previous_crop_options"] == ["Maize", "Rice"]
    assert cycle["seasons"] == ["Kharif", "Rabi", "Zaid"]
    assert cycle["sequence_data_available"] is False
    assert {item["crop"] for item in cycle["historical_crop_records"]} == {"Rice", "Maize"}
    assert all(item["source_url"].startswith("https://doi.org/") for item in cycle["historical_crop_records"])
    assert {item["crop"] for item in plan["candidates"]} == {"Rice", "Maize"}
