from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.config import settings as base_settings
from backend.data_service import (
    satellite_evidence,
    satellite_observation_for_district,
    soil_evidence,
    soil_observation_for_district,
)
from backend.main import create_app


def test_soil_and_satellite_observation_loaders():
    # Nalgonda
    soil_nalgonda = soil_observation_for_district("Nalgonda")
    assert soil_nalgonda["status"] == "available"
    assert soil_nalgonda["district"] == "Nalgonda"
    assert soil_nalgonda["verification_status"] == "verified_public_estimate"
    assert 0 <= soil_nalgonda["metrics"]["ph"] <= 14
    assert soil_nalgonda["prediction_interval_90_percent"]["ph"][0] < soil_nalgonda["metrics"]["ph"]
    assert "reference point" in soil_nalgonda["spatial_scope"]
    assert soil_nalgonda["live"] is False

    sat_nalgonda = satellite_observation_for_district("Nalgonda")
    assert sat_nalgonda["status"] == "available"
    assert sat_nalgonda["district"] == "Nalgonda"
    assert "mean_ndvi" in sat_nalgonda["metrics"]
    assert -1 <= sat_nalgonda["metrics"]["mean_ndvi"] <= 1
    assert sat_nalgonda["verification_status"] == "verified_public_observation"
    assert "Observation:" in sat_nalgonda["observation_vs_inference"]
    assert sat_nalgonda["live"] is False

    # Khammam
    soil_khammam = soil_observation_for_district("Khammam")
    # Provider returned null for this coordinate. A labelled fixture remains
    # available to the demo UI, but is not described as a verified result.
    assert soil_khammam["status"] == "available"
    assert soil_khammam["verification_status"] == "unverified_demo_fixture"

    sat_khammam = satellite_observation_for_district("Khammam")
    assert sat_khammam["status"] == "available"
    assert -1 <= sat_khammam["metrics"]["mean_ndvi"] <= 1

    # Krishna
    soil_krishna = soil_observation_for_district("Krishna")
    assert soil_krishna["status"] == "available"
    assert soil_krishna["state"] == "Andhra Pradesh"

    sat_krishna = satellite_observation_for_district("Krishna")
    assert sat_krishna["status"] == "available"
    assert sat_krishna["state"] == "Andhra Pradesh"

    # Unsupported district returns unavailable
    soil_unknown = soil_observation_for_district("UnknownDistrict")
    assert soil_unknown["status"] == "unavailable"
    assert soil_unknown["data_type"] == "missing"

    sat_unknown = satellite_observation_for_district("UnknownDistrict")
    assert sat_unknown["status"] == "unavailable"
    assert sat_unknown["data_type"] == "missing"


def test_evidence_packet_generation():
    nalgonda_field = {
        "id": "field-nalgonda-rice-1",
        "district": "Nalgonda",
        "state": "Telangana",
        "crop": "Rice",
    }
    s_ev = soil_evidence(nalgonda_field)
    assert s_ev is not None
    assert s_ev["type"] == "modelled_soil_estimate"
    assert s_ev["verification_status"] == "verified_public_estimate"
    assert s_ev["live"] is False

    sat_ev = satellite_evidence(nalgonda_field)
    assert sat_ev is not None
    assert sat_ev["type"] == "recorded_satellite_observation"
    assert "Sentinel-2 L2A" in sat_ev["label"]
    assert "Observation:" in sat_ev["observation_vs_inference"]
    assert sat_ev["live"] is False


def test_api_context_returns_soil_and_satellite_when_enabled(tmp_path: Path, monkeypatch):
    import backend.api as api_module
    import backend.config as config_module
    import backend.database as database_module
    import backend.security as security_module

    test_settings = replace(
        base_settings,
        database_path=tmp_path / "agrisathi.sqlite3",
        upload_dir=tmp_path / "private-uploads",
        session_secret="test-session-secret-that-is-long-enough",
        gemini_api_key="", enable_no_key_weather=False,
        openweather_api_key="",
        enable_recorded_observations=True,
        demo_mode=True,
    )
    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(api_module, "settings", test_settings)
    monkeypatch.setattr(database_module, "settings", test_settings)
    monkeypatch.setattr(security_module, "settings", test_settings)

    app = create_app()
    with TestClient(app) as client:
        client.post("/api/v1/session", json={"username": "ramesh", "password": "123"})
        field = client.get("/api/v1/fields").json()[0]
        context = client.get(f"/api/v1/fields/{field['id']}/context").json()

        assert context["soil"]["status"] == "available"
        assert context["soil"]["verification_status"] == "verified_public_estimate"
        assert 0 <= context["soil"]["metrics"]["ph"] <= 14
        assert context["climate"]["status"] == "available"
        assert context["climate"]["source_title"] == "NASA POWER daily meteorology"

        assert context["satellite"]["status"] == "available"
        assert -1 <= context["satellite"]["metrics"]["mean_ndvi"] <= 1
        assert context["satellite"]["verification_status"] == "verified_public_observation"

        # Check evidence packet contains the recorded soil and satellite observations
        evidence_types = {item["type"] for item in context["evidence"]}
        assert "modelled_soil_estimate" in evidence_types
        assert "recorded_satellite_observation" in evidence_types
