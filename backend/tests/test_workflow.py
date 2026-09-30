from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.config import settings as base_settings
from backend.main import create_app


def test_farmer_officer_exchange_and_second_farmer_flow(tmp_path: Path, monkeypatch):
    import backend.ai_service as ai_module
    import backend.api as api_module
    import backend.config as config_module
    import backend.database as database_module
    import backend.security as security_module
    import backend.weather_service as weather_module

    test_settings = replace(
        base_settings,
        database_path=tmp_path / "agrisathi.sqlite3",
        upload_dir=tmp_path / "private-uploads",
        session_secret="test-session-secret-that-is-long-enough",
        gemini_api_key="", enable_no_key_weather=False,
        openweather_api_key="",
        enable_recorded_observations=False,
        demo_mode=True,
    )
    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(ai_module, "settings", test_settings)
    monkeypatch.setattr(api_module, "settings", test_settings)
    monkeypatch.setattr(database_module, "settings", test_settings)
    monkeypatch.setattr(security_module, "settings", test_settings)
    monkeypatch.setattr(weather_module, "settings", test_settings)

    app = create_app()
    with TestClient(app) as client:
        unauthenticated = client.get("/api/v1/fields")
        assert unauthenticated.status_code == 401
        assert len(unauthenticated.headers["x-request-id"]) == 32
        farmer_login = client.post("/api/v1/session", json={"username": "ramesh", "password": "123"})
        assert farmer_login.status_code == 200
        field = client.get("/api/v1/fields").json()[0]
        context = client.get(f"/api/v1/fields/{field['id']}/context").json()
        assert context["historical"][0]["period"]
        assert context["weather"]["status"] == "unavailable"
        assert context["soil"]["status"] == "unavailable"
        assert context["satellite"]["status"] == "unavailable"

        image_stream = BytesIO()
        Image.new("RGB", (240, 160), color=(75, 130, 42)).save(image_stream, format="PNG")
        created = client.post(
            "/api/v1/cases",
            data={
                "field_id": field["id"],
                "question": "There are changing marks on the leaves. Can you help?",
                "transcript": "There are changing marks on the leaves. Can you help?",
                "language": "en",
                "submission_id": "retryable-test-case-0001",
            },
            files={"photo": ("leaf.png", image_stream.getvalue(), "image/png")},
        )
        assert created.status_code == 200, created.text
        case = created.json()
        assert case["provider"] == "demo-abstention"
        assert case["advisory"]["live_model_call"] is False
        assert case["status"] == "guidance_unavailable"
        assert case["photo_shared_with_officer"] is False
        assert client.get("/api/v1/officer/queue").status_code == 403
        assert client.post("/api/v1/session", json={"username": "rajesh", "password": "123"}).status_code == 200
        assert all(row["id"] != case["id"] for row in client.get("/api/v1/officer/queue").json())
        assert client.post("/api/v1/session", json={"username": "ramesh", "password": "123"}).status_code == 200

        repeated = client.post(
            "/api/v1/cases",
            data={
                "field_id": field["id"], "question": "retry", "language": "en",
                "submission_id": "retryable-test-case-0001",
            },
        )
        assert repeated.status_code == 200
        assert repeated.json()["id"] == case["id"]

        no_consent = client.post(f"/api/v1/cases/{case['id']}/contact-officer", data={
            "expected_version": 1, "name": "Demo Farmer", "phone": "9876543210",
            "location": "Nalgonda, Telangana", "query": "Please call about the leaf marks.", "consent": "false",
        })
        assert no_consent.status_code == 422
        contact = client.post(f"/api/v1/cases/{case['id']}/contact-officer", data={
            "expected_version": 1, "name": "Demo Farmer", "phone": "+91 98765 43210",
            "location": "Nalgonda, Telangana, Demo Village", "query": "Please call about the leaf marks.", "consent": "true",
        }, files={"photo": ("officer-leaf.png", image_stream.getvalue(), "image/png")})
        assert contact.status_code == 200, contact.text
        assert contact.json()["status"] == "needs_review"
        assert contact.json()["contact_requested"] is True
        assert "contact" not in contact.json()
        assert contact.json()["photo_shared_with_officer"] is True
        assert all("contact" not in item for item in client.get("/api/v1/cases/my").json())
        assert "contact" not in client.get(f"/api/v1/cases/{case['id']}").json()

        outsider = TestClient(app)
        outsider.post("/api/v1/session", json={"username": "suresh", "password": "123"})
        assert outsider.get(f"/api/v1/cases/{case['id']}").status_code == 404
        assert outsider.get(f"/api/v1/officer/cases/{case['id']}/photo").status_code == 403
        outsider.close()

        assert client.post("/api/v1/session", json={"username": "rajesh", "password": "123"}).status_code == 200
        queued = client.get("/api/v1/officer/queue").json()[0]
        assert queued["id"] == case["id"]
        assert queued["contact"] == {
            "name": "Demo Farmer", "phone": "919876543210", "location": "Nalgonda, Telangana, Demo Village",
            "query": "Please call about the leaf marks.", "requested_at": queued["contact"]["requested_at"],
        }
        photo_response = client.get(f"/api/v1/officer/cases/{case['id']}/photo")
        assert photo_response.status_code == 200
        assert photo_response.headers["content-type"] == "image/jpeg"

        approved = client.post(
            f"/api/v1/officer/cases/{case['id']}/review",
            json={"status": "approved", "note": "Photo received; advise local confirmation.", "expected_version": 2},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert approved.json()["contact"]["phone"] == "919876543210"
        review_history = client.get(f"/api/v1/officer/cases/{case['id']}/reviews")
        assert review_history.status_code == 200
        assert review_history.json()[0]["note"] == "Photo received; advise local confirmation."
        stale = client.post(
            f"/api/v1/officer/cases/{case['id']}/review",
            json={"status": "needs_information", "note": "stale", "expected_version": 1},
        )
        assert stale.status_code == 409

        # A new app instance against the same SQLite file models a process restart.
        with TestClient(create_app()) as restarted:
            assert restarted.post(
                "/api/v1/session", json={"username": "ramesh", "password": "123"},
            ).status_code == 200
            persisted = restarted.get("/api/v1/cases/my").json()
            persisted_case = next(item for item in persisted if item["id"] == case["id"])
            assert persisted_case["status"] == "approved"
            assert persisted_case["version"] == 3

        personal = client.post(
            "/api/v1/officer/advisories",
            json={
                "title": "Call farmer at 9876543210",
                "body": "This message includes a personal contact number and cannot be shared.",
                "valid_days": 14,
                "source_case_id": case["id"],
            },
        )
        assert personal.status_code == 422

        published = client.post(
            "/api/v1/officer/advisories",
            json={
                "title": "Rice leaf observations in Nalgonda",
                "body": "Photograph changing leaf marks and ask the local extension office to confirm the cause before changing treatment.",
                "valid_days": 14,
                "source_case_id": case["id"],
            },
        )
        assert published.status_code == 200, published.text
        advisory = published.json()
        # Publication itself delivers the PII-free regional share; no extra UI action.
        receipt_rows = client.get('/api/v1/officer/exchanges').json()
        assert len(receipt_rows) == 1
        assert receipt_rows[0]['payload']['title'] == advisory['title']
        shared = client.post(f"/api/v1/officer/advisories/{advisory['id']}/exchange", json={})
        assert shared.status_code == 200, shared.text
        assert shared.json()['duplicate'] is True
        payload = shared.json()["payload"]
        assert payload["source_state"] == "Telangana"
        assert payload["target_state"] == "Andhra Pradesh"
        assert payload["target_district"] == "Krishna"
        assert "farmer_id" not in payload and "question" not in payload and "photo" not in payload
        duplicate = client.post(f"/api/v1/officer/advisories/{advisory['id']}/exchange", json={})
        assert duplicate.status_code == 200 and duplicate.json()["duplicate"] is True

        client.post("/api/v1/session", json={"username": "lakshmi", "password": "123"})
        krishna_field = client.get("/api/v1/fields").json()[0]
        feed = client.get(f"/api/v1/fields/{krishna_field['id']}/feed").json()
        assert len(feed) == 1
        assert feed[0]["exchange_source"].startswith("Shared from Telangana")
        assert feed[0]["title"] == advisory["title"]
        maize_field = next(field for field in client.get('/api/v1/fields').json() if field['crop'] == 'Maize')
        assert client.get(f"/api/v1/fields/{maize_field['id']}/feed").json() == []

        client.post("/api/v1/session", json={"username": "anil", "password": "123"})
        khammam_field = client.get("/api/v1/fields").json()[0]
        assert khammam_field["crop"] == "Maize"
        assert client.get(f"/api/v1/fields/{khammam_field['id']}/feed").json() == []

        client.post("/api/v1/session", json={"username": "rajesh", "password": "123"})
        assert client.delete(f"/api/v1/cases/{case['id']}/photo").status_code == 200
        assert client.get(f"/api/v1/officer/cases/{case['id']}/photo").status_code == 404


def test_photo_validation_rejects_non_image_and_demo_sessions_are_signed(tmp_path: Path, monkeypatch):
    import backend.ai_service as ai_module
    import backend.api as api_module
    import backend.config as config_module
    import backend.database as database_module
    import backend.security as security_module

    test_settings = replace(
        base_settings,
        database_path=tmp_path / "test.sqlite3",
        upload_dir=tmp_path / "uploads",
        session_secret="different-test-secret",
        gemini_api_key="", enable_no_key_weather=False,
        demo_mode=True,
    )
    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(ai_module, "settings", test_settings)
    monkeypatch.setattr(api_module, "settings", test_settings)
    monkeypatch.setattr(database_module, "settings", test_settings)
    monkeypatch.setattr(security_module, "settings", test_settings)
    with TestClient(create_app()) as client:
        client.post("/api/v1/session", json={"username": "ramesh", "password": "123"})
        field = client.get("/api/v1/fields").json()[0]
        invalid = client.post(
            "/api/v1/cases",
            data={"field_id": field["id"], "question": "Please check these leaf changes."},
            files={"photo": ("fake.png", b"not an image", "image/png")},
        )
        assert invalid.status_code == 415
        token = client.cookies.get("agrisathi_session")
        client.cookies.set("agrisathi_session", f"{token}tampered", domain="testserver.local")
        assert client.get("/api/v1/fields").status_code == 401


def test_officer_can_request_information_then_reject_without_publishing(tmp_path: Path, monkeypatch):
    import backend.ai_service as ai_module
    import backend.api as api_module
    import backend.config as config_module
    import backend.database as database_module
    import backend.security as security_module
    import backend.weather_service as weather_module

    test_settings = replace(
        base_settings,
        database_path=tmp_path / "review-path.sqlite3",
        upload_dir=tmp_path / "uploads",
        session_secret="review-path-test-secret-that-is-long-enough",
        gemini_api_key="", enable_no_key_weather=False,
        openweather_api_key="",
        demo_mode=True,
    )
    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(ai_module, "settings", test_settings)
    monkeypatch.setattr(api_module, "settings", test_settings)
    monkeypatch.setattr(database_module, "settings", test_settings)
    monkeypatch.setattr(security_module, "settings", test_settings)
    monkeypatch.setattr(weather_module, "settings", test_settings)

    with TestClient(create_app()) as client:
        assert client.post(
            "/api/v1/session", json={"username": "ramesh", "password": "123"},
        ).status_code == 200
        field = client.get("/api/v1/fields").json()[0]
        created = client.post("/api/v1/cases", data={
            "field_id": field["id"], "question": "The rice leaves changed color this week.", "language": "en",
        })
        assert created.status_code == 200, created.text
        case = created.json()

        assert client.post(
            "/api/v1/session", json={"username": "rajesh", "password": "123"},
        ).status_code == 200
        needs_information = client.post(
            f"/api/v1/officer/cases/{case['id']}/review",
            json={"status": "needs_information", "note": "Please add a dated field photo.", "expected_version": 1},
        )
        assert needs_information.status_code == 200
        assert needs_information.json()["status"] == "needs_information"
        assert needs_information.json()["reviews"][0]["note"] == "Please add a dated field photo."
        rejected = client.post(
            f"/api/v1/officer/cases/{case['id']}/review",
            json={"status": "rejected", "note": "No follow-up evidence received.", "expected_version": 2},
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "rejected"
        closed = client.post(
            f"/api/v1/officer/cases/{case['id']}/review",
            json={"status": "resolved", "note": "Closed case cannot change.", "expected_version": 3},
        )
        assert closed.status_code == 409
        assert client.get("/api/v1/officer/advisories").json() == []

        assert client.post(
            "/api/v1/session", json={"username": "ramesh", "password": "123"},
        ).status_code == 200
        farmer_cases = client.get("/api/v1/cases/my").json()
        assert farmer_cases[0]["status"] == "rejected"
        assert farmer_cases[0]["reviews"][-1]["note"] == "No follow-up evidence received."


def test_direct_answer_can_be_escalated_and_farmer_can_reply(tmp_path: Path, monkeypatch):
    import backend.ai_service as ai_module
    import backend.api as api_module
    import backend.config as config_module
    import backend.database as database_module
    import backend.security as security_module

    test_settings = replace(base_settings, database_path=tmp_path / "direct.sqlite3", upload_dir=tmp_path / "uploads",
        session_secret="direct-flow-test-secret-long-enough", gemini_api_key="", enable_no_key_weather=False, demo_mode=True)
    for module in (config_module, api_module, database_module, security_module, ai_module):
        monkeypatch.setattr(module, "settings", test_settings)
    with TestClient(create_app()) as client:
        client.post("/api/v1/session", json={"username": "ramesh", "password": "123"})
        field = client.get("/api/v1/fields").json()[0]
        # Mock a valid routine Gemini answer: it should be available immediately.
        async def routine(*args, **kwargs):
            return {"summary": "Observe which leaves changed first.", "summary_source_ids": [], "possible_causes": [],
                    "uncertainty": "A field inspection is needed for diagnosis.", "actions": [],
                    "needs_officer_review": False, "answer_basis": "general", "provider": "Google Gemini API", "model": "mock-flash", "live_model_call": True}
        monkeypatch.setattr(ai_module, "generate_advisory", routine)
        monkeypatch.setattr(api_module, "generate_advisory", routine)
        created = client.post("/api/v1/cases", data={"field_id": field["id"], "question": "What should I observe on the rice leaves?", "language": "en"}).json()
        assert created["status"] == "answered"
        assert created["advisory"]["needs_officer_review"] is False
        retired = client.post(f"/api/v1/cases/{created['id']}/review-request", json={"expected_version": 1})
        assert retired.status_code == 410
        assert client.get("/api/v1/cases/my").json()[0]["status"] == "answered"
        escalated = client.post(f"/api/v1/cases/{created['id']}/contact-officer", data={
            "expected_version": 1, "name": "Nalgonda Farmer", "phone": "9876501234",
            "location": "Nalgonda, Telangana", "query": "Please confirm what I should observe next.", "consent": "true",
        })
        assert escalated.status_code == 200 and escalated.json()["status"] == "needs_review"
        assert client.post("/api/v1/session", json={"username": "rajesh", "password": "123"}).status_code == 200
        assert any(row["id"] == created["id"] for row in client.get("/api/v1/officer/queue").json())
        requested = client.post(f"/api/v1/officer/cases/{created['id']}/review", json={"status": "needs_information", "note": "When did this start?", "expected_version": 2})
        assert requested.status_code == 200
        assert requested.json()["reviews"][0]["note"] == "When did this start?"
        client.post("/api/v1/session", json={"username": "ramesh", "password": "123"})
        reply = client.post(f"/api/v1/cases/{created['id']}/reply", json={"text": "It began about four days ago.", "expected_version": 3})
        assert reply.status_code == 200
        assert reply.json()["status"] == "needs_review"
        assert reply.json()["messages"][0]["body"] == "It began about four days ago."


def test_officer_state_scope_is_enforced(tmp_path: Path, monkeypatch):
    import backend.api as api_module
    import backend.config as config_module
    import backend.database as database_module
    import backend.security as security_module
    scoped = replace(base_settings, database_path=tmp_path / "scope.sqlite3", session_secret="scope-test-secret-long-enough",
                     demo_mode=True, gemini_api_key="", enable_no_key_weather=False, openweather_api_key="")
    for module in (config_module, api_module, database_module, security_module):
        monkeypatch.setattr(module, "settings", scoped)
    with TestClient(create_app()) as client:
        assert client.post("/api/v1/session", json={"username": "lakshmi", "password": "123"}).status_code == 200
        field = client.get("/api/v1/fields").json()[0]
        case = client.post("/api/v1/cases", data={
            "field_id": field["id"], "question": "Please help with these Krishna rice leaves.", "language": "en",
        })
        assert case.status_code == 200 and case.json()["status"] == "guidance_unavailable"
        case_id = case.json()["id"]
        contact = client.post(f"/api/v1/cases/{case_id}/contact-officer", data={
            "expected_version": 1, "name": "AP Demo Farmer", "phone": "9876543210",
            "location": "Krishna, Andhra Pradesh", "query": "Please help with these rice leaves.", "consent": "true",
        })
        assert contact.status_code == 200 and contact.json()["status"] == "needs_review"
        assert client.post("/api/v1/session", json={"username": "priya", "password": "123"}).status_code == 200
        assert any(row["id"] == case_id for row in client.get("/api/v1/officer/queue").json())
        assert client.post("/api/v1/session", json={"username": "priya", "password": "123"}).status_code == 200
        assert client.get("/api/v1/officer/advisories").json() == []
        assert client.get(f"/api/v1/officer/cases/{case_id}/reviews").status_code == 200
        assert client.post("/api/v1/session", json={"username": "rajesh", "password": "123"}).status_code == 200
        assert not any(row["id"] == case_id for row in client.get("/api/v1/officer/queue").json())
        assert client.get(f"/api/v1/officer/cases/{case_id}/reviews").status_code == 403
        assert client.post("/api/v1/session", json={"username": "unknown", "password": "123"}).status_code == 401


def test_officer_cannot_create_a_farmer_case_or_be_silently_switched(tmp_path: Path, monkeypatch):
    import backend.api as api_module
    import backend.config as config_module
    import backend.database as database_module
    import backend.security as security_module
    import backend.weather_service as weather_module

    scoped = replace(
        base_settings,
        database_path=tmp_path / "officer-case.sqlite3",
        upload_dir=tmp_path / "uploads",
        session_secret="officer-case-test-secret-long-enough",
        demo_mode=True,
        gemini_api_key="", enable_no_key_weather=False,
        openweather_api_key="",
    )
    for module in (config_module, api_module, database_module, security_module, weather_module):
        monkeypatch.setattr(module, "settings", scoped)

    with TestClient(create_app()) as client:
        login = client.post("/api/v1/session", json={"username": "rajesh", "password": "123"})
        assert login.status_code == 200
        original_cookie = client.cookies.get("agrisathi_session")
        response = client.post("/api/v1/cases", data={
            "field_id": "field-nalgonda-rice-1",
            "question": "Please inspect this farmer question.",
            "language": "en",
        })
        assert response.status_code == 403
        assert client.cookies.get("agrisathi_session") == original_cookie
        assert client.get("/api/v1/session").json()["identity"]["role"] == "officer"


def test_expired_demo_session_is_not_authenticated(tmp_path: Path, monkeypatch):
    import hashlib
    import hmac
    import json
    import time

    import backend.api as api_module
    import backend.config as config_module
    import backend.database as database_module
    import backend.security as security_module

    scoped = replace(
        base_settings,
        database_path=tmp_path / "expired-session.sqlite3",
        session_secret="expired-session-test-secret-long-enough",
        demo_mode=True,
        gemini_api_key="", enable_no_key_weather=False,
        openweather_api_key="",
    )
    for module in (config_module, api_module, database_module, security_module):
        monkeypatch.setattr(module, "settings", scoped)

    expired_payload = json.dumps(
        {"role": "farmer", "actor_id": "farmer-nalgonda-1", "issued_at": int(time.time()) - 13 * 60 * 60},
        separators=(",", ":"), sort_keys=True,
    ).encode()
    body = security_module._b64(expired_payload)
    signature = security_module._b64(
        hmac.new(scoped.session_secret.encode(), body.encode(), hashlib.sha256).digest()
    )
    expired_cookie = f"{body}.{signature}"

    with TestClient(create_app()) as client:
        session = client.get("/api/v1/session", cookies={"agrisathi_session": expired_cookie})
        assert session.status_code == 200
        assert session.json()["authenticated"] is False
        assert client.get("/api/v1/fields", cookies={"agrisathi_session": expired_cookie}).status_code == 401
