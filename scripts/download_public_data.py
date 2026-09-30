"""Download bounded reference-point evidence; never claim district/plot coverage.

Run with Python and requirements-data.txt. Raw responses and small raster windows
are retained to reproduce every number. Failures leave that source unavailable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCATIONS = {
    "Nalgonda": {"state": "Telangana", "lat": 17.00, "lon": 79.30},
    "Khammam": {"state": "Telangana", "lat": 17.25, "lon": 80.12},
    "Krishna": {"state": "Andhra Pradesh", "lat": 16.30, "lon": 81.05},
}


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "AgriSaathi-prototype/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        content = response.read(2_000_001)
    if len(content) > 2_000_000:
        raise ValueError("Response exceeds the bounded download limit")
    return json.loads(content)


def save(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def soil(url: str, raw: dict, base: dict) -> dict:
    metrics, intervals = {}, {}
    for layer in raw["properties"]["layers"]:
        values = layer["depths"][0]["values"]
        factor = layer["unit_measure"]["d_factor"]
        key = {"phh2o": "ph", "soc": "organic_carbon_percent"}[layer["name"]]
        # SOC target g/kg -> percent: /10 after the provider's storage scaling.
        divisor = factor * (10 if layer["name"] == "soc" else 1)
        metrics[key] = values.get("mean") / divisor if values.get("mean") is not None else None
        intervals[key] = [values.get(q) / divisor if values.get(q) is not None else None for q in ("Q0.05", "Q0.95")]
    if not any(value is not None for value in metrics.values()):
        raise ValueError("SoilGrids returned only missing values")
    return {
        **base, "id": f"soilgrids-{base['district'].lower()}-0-5cm", "status": "available",
        "data_type": "modelled_soil_estimate", "verification_status": "verified_public_estimate",
        "soil_class": "SoilGrids modelled topsoil (0–5 cm)", "metrics": metrics,
        "prediction_interval_90_percent": intervals, "observed_at": None,
        "source_title": "ISRIC SoilGrids 2.0", "source_url": "https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs.html",
        "request_url": url, "report_id": None, "live": False,
        "processing_method": "Mean and 5th/95th quantile at 0–5 cm. Provider storage scaling applied; SOC g/kg converted to percent.",
        "warning": "Modelled 250 m soil estimate at a reference point, not a farmer's soil test. N/P/K availability and EC are unavailable. Wide prediction intervals limit interpretation.",
        "provenance_notes": "Prediction dataset, not a dated laboratory observation. Download date is not sample date.",
    }


def climate(url: str, raw: dict, base: dict) -> dict:
    params = raw["properties"]["parameter"]
    fill = raw["header"]["fill_value"]
    units = {key: raw["parameters"][key]["units"] for key in params}
    values = {key: [v for v in series.values() if v != fill] for key, series in params.items()}
    return {
        **base, "id": f"nasa-power-{base['district'].lower()}-202508", "status": "available",
        "type": "historical_climate_estimate", "label": "NASA POWER August 2025 climate reference",
        "period": "2025-08-01 to 2025-08-31", "units": units,
        "values": {"mean_temperature_c": round(statistics.mean(values["T2M"]), 2),
                   "mean_atmospheric_humidity_percent": round(statistics.mean(values["RH2M"]), 2),
                   "total_precipitation_mm": round(sum(values["PRECTOTCORR"]), 2)},
        "valid_days": {key: len(series) for key, series in values.items()},
        "verification_status": "verified_public_estimate", "source_title": "NASA POWER daily meteorology",
        "source_url": "https://power.larc.nasa.gov/docs/services/api/temporal/daily/", "request_url": url,
        "warning": "Historical gridded meteorology at a reference point; not today's weather, a forecast, or a farm rain gauge.",
        "live": False,
    }


def satellite(base: dict, output: Path) -> dict:
    import numpy as np
    import rasterio
    from rasterio.warp import transform
    from rasterio.windows import Window

    lat, lon = base["reference_point"]["latitude"], base["reference_point"]["longitude"]
    query = urllib.parse.urlencode({"collections": "sentinel-2-l2a", "bbox": f"{lon-.005},{lat-.005},{lon+.005},{lat+.005}",
                                  "datetime": "2025-08-01T00:00:00Z/2025-10-31T23:59:59Z", "limit": 30})
    search_url = "https://earth-search.aws.element84.com/v1/search?" + query
    result = get_json(search_url)
    # Deterministic best scene among this bounded candidate page, not entire archive.
    candidates = sorted(result.get("features", []), key=lambda item: (item["properties"].get("eo:cloud_cover", 100), item["id"]))
    if not candidates:
        raise ValueError("No Sentinel-2 scenes in the bounded search")
    selected = candidates[0]
    save(output / "sentinel-scene.json", selected)
    save(output / "sentinel-search.json", {
        "request_url": search_url,
        "candidate_count_on_first_page": len(result.get("features", [])),
        "selected_scene_id": selected["id"],
        "selection": "Lowest scene cloud cover in the first returned candidate page; bounded point search only.",
    })
    arrays, metadata, crop_bounds = {}, {}, None
    # Use HTTP range reads of COGs, never download whole scenes.
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_TIMEOUT="40", GDAL_HTTP_MAX_RETRY="1"):
        for band in ("red", "nir", "scl"):
            asset = selected["assets"][band]
            with rasterio.open(asset["href"]) as src:
                x, y = transform("EPSG:4326", src.crs, [lon], [lat])
                row, col = src.index(x[0], y[0])
                size = 100 if band != "scl" else 50  # 1 km square, 10/20 m pixels
                start_col, start_row = col-size//2, row-size//2
                if band != "scl":
                    # Align to the 20 m SCL grid before nearest-neighbour expansion.
                    start_col, start_row = (start_col//2)*2, (start_row//2)*2
                window = Window(start_col, start_row, size, size)
                data = src.read(1, window=window)
                if data.shape != (size, size):
                    raise ValueError("Reference window crosses scene boundary")
                profile = src.profile.copy()
                profile.update(width=size, height=size, transform=src.window_transform(window), tiled=False, compress="deflate")
                profile.pop("blockxsize", None)
                profile.pop("blockysize", None)
                path = output / f"sentinel-{band}.tif"
                with rasterio.open(path, "w", **profile) as dst:
                    dst.write(data, 1)
                metadata[band] = {"href": asset["href"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "scale": asset.get("raster:bands", [{}])[0].get("scale", 0.0001),
                                  "offset": asset.get("raster:bands", [{}])[0].get("offset", 0)}
                arrays[band] = data
                if band == "red":
                    crop_bounds = {"crs": str(src.crs), "bounds": list(src.window_bounds(window))}
    red = arrays["red"].astype(float) * metadata["red"]["scale"] + metadata["red"]["offset"]
    nir = arrays["nir"].astype(float) * metadata["nir"]["scale"] + metadata["nir"]["offset"]
    scl = np.repeat(np.repeat(arrays["scl"], 2, axis=0), 2, axis=1)
    valid = np.isin(scl, [4, 5]) & (arrays["red"] > 0) & (arrays["nir"] > 0) & (red >= 0) & (nir >= 0) & ((red+nir) > 1e-6)
    if valid.sum() < 100:
        raise ValueError("Too few usable vegetation/bare-soil pixels")
    ndvi = (nir[valid]-red[valid]) / (nir[valid]+red[valid])
    if not np.isfinite(ndvi).all() or np.any(np.abs(ndvi) > 1):
        raise ValueError("NDVI failed physical range validation")
    return {
        **base, "id": f"sentinel-{base['district'].lower()}-{selected['id']}", "status": "available",
        "data_type": "recorded_satellite_observation", "verification_status": "verified_public_observation",
        "sensor": "Sentinel-2 L2A · 1 km reference window", "scene_id": selected["id"],
        "observed_at": selected["properties"]["datetime"], "geographic_bounds": crop_bounds,
        "metrics": {"mean_ndvi": round(float(ndvi.mean()), 4), "valid_pixel_count": int(valid.sum()),
                    "valid_land_pixel_percent": round(float(valid.mean()*100), 2)},
        "processing_method": "NDVI=(NIR-Red)/(NIR+Red), asset reflectance scale/offset; SCL classes 4/5 only. SCL nearest-neighbour 20 m to 10 m.",
        "source_title": "Copernicus Sentinel-2 L2A via Element 84 Earth Search", "source_url": "https://github.com/Element84/earth-search",
        "request_url": search_url, "asset_metadata": metadata, "live": False,
        "warning": "Archived 2025 reference-area observation, not a current district average or farmer plot. No crop mask; no disease diagnosis, anomaly, or VCI is derived.",
        "observation_vs_inference": "Observation: reflectance-derived greenness over valid reference-window pixels. It cannot establish crop identity, disease, irrigation need, or nutrient deficiency.",
        "provenance_notes": "Original STAC metadata and three small raster windows are retained for reproducibility.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", nargs="+", choices=["soil", "climate", "satellite"], default=["soil", "climate", "satellite"])
    args = parser.parse_args()
    target = ROOT / "backend/data/public"
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"version": "public-reference-v1", "locations": LOCATIONS, "downloads": {}}
    manifest["locations"] = LOCATIONS
    for district, location in LOCATIONS.items():
        base = {"district": district, "state": location["state"],
                "reference_point": {"latitude": location["lat"], "longitude": location["lon"]},
                "spatial_scope": "Selected reference point/window near the named district; not a district aggregate or registered farmer plot."}
        output = target / district.lower()
        for source in args.sources:
            key = f"{district}/{source}"
            try:
                if source == "satellite":
                    normalized = satellite(base, output)
                else:
                    params = {"lon": location["lon"], "lat": location["lat"], "property": ["phh2o", "soc"], "depth": "0-5cm", "value": ["mean", "Q0.05", "Q0.95"]} if source == "soil" else {
                        "longitude": location["lon"], "latitude": location["lat"], "parameters": "T2M,RH2M,PRECTOTCORR", "community": "AG", "start": "20250801", "end": "20250831", "format": "JSON"}
                    endpoint = "https://rest.isric.org/soilgrids/v2.0/properties/query?" if source == "soil" else "https://power.larc.nasa.gov/api/temporal/daily/point?"
                    url = endpoint + urllib.parse.urlencode(params, doseq=True)
                    raw = get_json(url)
                    raw_hash = save(output / f"{source}-raw.json", raw)
                    normalized = (soil if source == "soil" else climate)(url, raw, base)
                    normalized["raw_sha256"] = raw_hash
                normalized["downloaded_at"] = datetime.now(timezone.utc).isoformat()
                digest = save(output / f"{source}.json", normalized)
                manifest["downloads"][key] = {"status": "available", "sha256": digest, "request_url": normalized["request_url"], "downloaded_at": normalized["downloaded_at"]}
                print(key, "downloaded", flush=True)
            except Exception as exc:
                manifest["downloads"][key] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
                print(key, "unavailable:", type(exc).__name__, str(exc), flush=True)
            save(manifest_path, manifest)


if __name__ == "__main__":
    main()
