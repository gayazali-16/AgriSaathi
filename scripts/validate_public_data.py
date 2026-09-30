"""Validate bounded public data files, provenance hashes and derived-value ranges."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend" / "data" / "public"
EXPECTED = {"Nalgonda", "Khammam", "Krishna"}


def main() -> None:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["locations"]) == EXPECTED
    assert len(manifest["downloads"]) == len(EXPECTED) * 3
    for district in sorted(EXPECTED):
        folder = DATA / district.lower()
        for source in ("climate", "soil", "satellite"):
            item = manifest["downloads"][f"{district}/{source}"]
            if item["status"] == "failed":
                assert source == "soil" and district == "Khammam", f"Unexpected failed sample: {district}/{source}"
                print(f"{district}/{source}: documented unavailable")
                continue
            path = folder / f"{source}.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], f"{district}/{source} digest mismatch"
            assert record["district"] == district and record["status"] == "available"
            assert record["reference_point"]["latitude"] == manifest["locations"][district]["lat"]
            assert record["reference_point"]["longitude"] == manifest["locations"][district]["lon"]
            if source == "satellite":
                assert -1 <= record["metrics"]["mean_ndvi"] <= 1
                assert record["metrics"]["valid_pixel_count"] > 0
                for band in ("red", "nir", "scl"):
                    asset = folder / f"sentinel-{band}.tif"
                    assert asset.is_file() and asset.stat().st_size < 100_000, f"Raster sample too large: {asset}"
                assert record["scene_id"]
            elif source == "soil":
                assert record["verification_status"] == "verified_public_estimate"
                assert 0 <= record["metrics"]["ph"] <= 14
                low, high = record["prediction_interval_90_percent"]["ph"]
                assert low <= record["metrics"]["ph"] <= high
            else:
                assert record["period"] == "2025-08-01 to 2025-08-31"
                assert record["valid_days"]["T2M"] == 31
        print(f"{district}: source artifacts validated")
    print("Public data provenance and bounds validated.")


if __name__ == "__main__":
    main()
