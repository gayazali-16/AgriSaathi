"""Seed one explicitly synthetic consented case via the real application API."""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from backend import ai_service, api, config, database, security, weather_service
from backend.main import create_app

SUBMISSION_ID = "judge-rehearsal-synthetic-v1"
QUESTION = "Judge rehearsal: lower rice leaves have changed color. What should I observe before discussing treatment?"


def seed(database_path: Path) -> dict:
    modules = [config, database, api, security, ai_service, weather_service]
    previous = [(module, module.settings) for module in modules]
    configured = replace(config.settings, database_path=database_path.resolve(),
                         gemini_api_key="", openweather_api_key="", enable_no_key_weather=False,
                         demo_mode=True)
    try:
        for module in modules:
            module.settings = configured
        # HTTPS also accepts Secure demo cookies if APP_ENV=production.
        with TestClient(create_app(), base_url="https://judge.local") as client:
            login = client.post("/api/v1/session", json={"username": "ramesh", "password": "123"})
            login.raise_for_status()
            created = client.post("/api/v1/cases", data={
                "field_id": "field-nalgonda-rice-1", "question": QUESTION,
                "language": "en", "submission_id": SUBMISSION_ID,
            })
            created.raise_for_status()
            case = created.json()
            if not case["contact_requested"] and case["status"] not in {"resolved", "rejected"}:
                contacted = client.post(f"/api/v1/cases/{case['id']}/contact-officer", data={
                    "expected_version": case["version"], "name": "Synthetic judge rehearsal",
                    "phone": "9999999999", "location": "Synthetic Nalgonda demo location",
                    "query": QUESTION, "consent": "true",
                })
                contacted.raise_for_status()
                case = contacted.json()
            return {"case_id": case["id"], "status": case["status"], "version": case["version"],
                    "synthetic_only": True, "live_model_call": case["advisory"]["live_model_call"]}
    finally:
        for module, previous_settings in previous:
            module.settings = previous_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True,
                        help="Explicit demo database. Use the same DATABASE_PATH when starting the server.")
    args = parser.parse_args()
    import json
    print(json.dumps(seed(args.database)))


if __name__ == "__main__":
    main()
