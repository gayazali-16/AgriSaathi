import logging
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import settings as base_settings
from backend.main import create_app


def test_request_id_is_returned_and_query_values_are_not_logged(tmp_path: Path, monkeypatch, caplog):
    import backend.database as database_module

    monkeypatch.setattr(database_module, "settings", replace(
        base_settings, database_path=tmp_path / "observability.sqlite3",
    ))
    with caplog.at_level(logging.INFO, logger="agrisathi.request"):
        with TestClient(create_app()) as client:
            response = client.get("/api/v1/health?private=do-not-log")

    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32
    records = [record for record in caplog.records if record.name == "agrisathi.request"]
    assert len(records) == 1
    assert records[0].request_id == request_id
    assert records[0].path == "/api/v1/health"
    assert records[0].status_code == 200
    assert "do-not-log" not in caplog.text
