from __future__ import annotations

import io
import os
import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.ai_service import PROMPT_VERSION, generate_advisory
from backend.config import settings
from backend.data_service import (
    DATASET_URL,
    artifact_manifest,
    climate_evidence,
    districts,
    evidence_for_field,
    planning_for_field,
    practice_evidence,
    satellite_evidence,
    satellite_observation_for_district,
    soil_evidence,
    soil_observation_for_district,
)
from backend.database import connect, json_dumps, row_dict, utc_now
from backend.exchange import STATE_ADAPTERS, build_regional_contract
from backend.schemas import DemoSessionRequest, FarmerReplyRequest, PublishAdvisoryRequest, ReviewRequest
from backend.security import (
    COOKIE_NAME,
    officer_state,
    current_identity,
    issue_session,
    demo_login,
    require_farmer,
    require_officer,
)
from backend.weather_service import current_weather

router = APIRouter(prefix="/api/v1")
LANGUAGE_CODES = {"en", "te", "hi"}
PHOTO_EVIDENCE_ID = "user-photo"


def _json_value(row: dict, key: str) -> object:
    return json.loads(row[key]) if row.get(key) else None


def _case_dict(row: dict) -> dict:
    return {
        **row,
        "advisory": _json_value(row, "advisory_json"),
        "evidence": _json_value(row, "evidence_json"),
        "photo_shared_with_officer": bool(row["photo_shared"]),
    }


def _case_payload(row: dict, include_contact: bool = False) -> dict:
    case = _case_dict(row)
    with connect() as db:
        reviews = db.execute("SELECT status, note, ai_decision, created_at, case_version FROM reviews WHERE case_id=? ORDER BY case_version", (row["id"],)).fetchall()
        messages = db.execute("SELECT body, created_at FROM case_messages WHERE case_id=? ORDER BY created_at, id", (row["id"],)).fetchall()
    payload = {
        "id": case["id"],
        "field_id": case["field_id"],
        "state": case["state"],
        "district": case["district"],
        "crop": case["crop"],
        "question": case["question"],
        "transcript": case["transcript"],
        "status": case["status"],
        "provider": case["provider"],
        "model": case["model"],
        "advisory": case["advisory"],
        "evidence": case["evidence"],
        "photo_shared_with_officer": case["photo_shared_with_officer"],
        "contact_requested": bool(case.get("contact_requested_at")),
        "created_at": case["created_at"],
        "version": case["version"],
        "reviews": [dict(item) for item in reviews],
        "messages": [dict(item) for item in messages],
    }
    if include_contact and case.get("contact_requested_at"):
        payload["contact"] = {
            "name": case.get("contact_name"),
            "phone": case.get("contact_phone"),
            "location": case.get("contact_location"),
            "query": case.get("contact_query"),
            "requested_at": case.get("contact_requested_at"),
        }
    return payload


def _load_field_for_owner(field_id: str, owner_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM fields WHERE id=? AND owner_id=?", (field_id, owner_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Field not found for this farmer.")
    return dict(row)


def _load_case(case_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return dict(row)


def _check_case_access(row: dict, identity: dict) -> None:
    if identity["role"] == "officer":
        if row["state"] != officer_state(identity):
            raise HTTPException(status_code=403, detail="This case is outside the officer's state scope.")
        return
    if row["owner_id"] != identity["actor_id"]:
        raise HTTPException(status_code=404, detail="Case not found for this farmer.")


def _private_image(data: bytes) -> tuple[bytes, dict]:
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > 24_000_000:
                raise HTTPException(status_code=413, detail="Image dimensions are too large.")
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(status_code=415, detail="Use a JPEG, PNG, or WebP image.")
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=86, optimize=True)
            return output.getvalue(), {"mime_type": "image/jpeg", "width": image.width, "height": image.height}
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=415, detail="The uploaded file is not a supported image.") from exc


def _sensitive_public_text(text: str) -> bool:
    patterns = [
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        r"(?:\+?91[\s-]?)?[6-9]\d{9}",
        r"farmer-(?:nalgonda|khammam|krishna)-\d+",
        r"field-[a-z]+-(?:rice|maize)-\d+",
    ]
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


async def _context_payload(field: dict) -> dict:
    historical = evidence_for_field(field)
    weather = await current_weather(field["district"])
    weather_evidence = []
    if weather.get("status") == "available":
        estimated = weather.get("data_type") == "live_provider_estimate"
        weather_evidence.append({
            "id": f"weather-{field['district'].casefold()}-{weather['observed_at']}",
            "type": "live_weather_estimate" if estimated else "live_weather_observation",
            "verification_status": "verified_public_estimate" if estimated else "live_provider_observation",
            "label": "Current weather-model estimate" if estimated else "Current reference-location weather",
            "scope": weather["spatial_scope"],
            "observed_at": weather["observed_at"],
            "values": {
                "temperature_c": weather["temperature_c"],
                "atmospheric_humidity_percent": weather["atmospheric_humidity_percent"],
                "rainfall_last_hour_mm": weather["rainfall_last_hour_mm"],
                "cloud_cover_percent": weather["cloud_cover_percent"],
            },
            "source_title": "Open-Meteo weather models" if estimated else "OpenWeather current weather endpoint",
            "source_url": "https://open-meteo.com/en/docs" if estimated else "https://openweathermap.org/current",
            "live": True,
            "warning": ("Weather-model estimate at a district reference point, not a station observation or field measurement. Atmospheric humidity is not soil moisture."
                        if estimated else "Reference-town observation; not the farmer's exact field. Cloud cover is not rainfall probability; atmospheric humidity is not soil moisture."),
        })

    extra_evidence = []
    climate = climate_evidence(field)
    if climate:
        extra_evidence.append(climate)
    if settings.enable_recorded_observations:
        soil = soil_observation_for_district(field["district"])
        satellite = satellite_observation_for_district(field["district"])
        s_ev = soil_evidence(field)
        if s_ev:
            extra_evidence.append(s_ev)
        sat_ev = satellite_evidence(field)
        if sat_ev:
            extra_evidence.append(sat_ev)
    else:
        soil = {"status": "unavailable", "reason": "No plot-level soil test is connected.", "live": False}
        satellite = {"status": "unavailable", "reason": "No dated satellite export is connected.", "live": False}

    return {
        "field": {
            "id": field["id"], "state": field["state"], "district": field["district"],
            "crop": field["crop"], "season": field["season"], "stage": field["stage"],
            "spatial_scope": field["spatial_scope"], "demo_profile": bool(field["demo_profile"]),
        },
        "historical": historical,
        "weather": weather,
        "soil": soil,
        "satellite": satellite,
        "climate": climate,
        "evidence": historical + weather_evidence + extra_evidence,
        "data_policy": "Historical values are not current field measurements. Unknown values are not imputed.",
    }


@router.get("/health")
async def health() -> dict:
    try:
        with connect() as db:
            db.execute("SELECT 1 FROM fields LIMIT 1")
    except sqlite3.Error:
        raise HTTPException(status_code=503, detail="Application storage is unavailable.")
    return {
        "status": "ok",
        "provider": "Google Gemini API" if settings.gemini_api_key else "demo abstention",
        "live_gemini_configured": bool(settings.gemini_api_key),
        "persistence": "local SQLite",
        "demo_mode": settings.demo_mode,
    }


@router.get("/session")
async def get_session(request: Request) -> dict:
    from backend.security import verify_session

    identity = verify_session(request.cookies.get(COOKIE_NAME, ""))
    return {"authenticated": identity is not None, "identity": identity, "demo_mode": settings.demo_mode}


@router.post("/session")
async def start_demo_session(payload: DemoSessionRequest, request: Request, response: Response) -> dict:
    if not settings.demo_mode:
        raise HTTPException(status_code=503, detail="Production identity is not configured.")
    role, actor_id = demo_login(payload.username, payload.password)
    token = issue_session(role, actor_id)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=request.url.scheme == "https" or os.getenv("APP_ENV") == "production", samesite="strict", max_age=12 * 60 * 60,
        path="/",
    )
    return {"authenticated": True, "identity": {"role": role, "actor_id": actor_id}, "demo_mode": True}


@router.delete("/session")
async def end_session(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"authenticated": False}


@router.get("/fields")
async def list_fields(identity: dict = Depends(current_identity)) -> list[dict]:
    require_farmer(identity)
    with connect() as db:
        rows = db.execute("SELECT * FROM fields WHERE owner_id=? ORDER BY id", (identity["actor_id"],)).fetchall()
    return [dict(row) for row in rows]


@router.get("/fields/{field_id}/context")
async def field_context(field_id: str, identity: dict = Depends(current_identity)) -> dict:
    require_farmer(identity)
    field = _load_field_for_owner(field_id, identity["actor_id"])
    return await _context_payload(field)


@router.get("/fields/{field_id}/planning")
async def field_planning(
    field_id: str,
    language: str = Query(default="en", pattern="^(en|hi|te)$"),
    identity: dict = Depends(current_identity),
) -> dict:
    require_farmer(identity)
    field = _load_field_for_owner(field_id, identity["actor_id"])
    return planning_for_field(field, language)


@router.get("/fields/{field_id}/feed")
async def farmer_feed(field_id: str, identity: dict = Depends(current_identity)) -> list[dict]:
    require_farmer(identity)
    field = _load_field_for_owner(field_id, identity["actor_id"])
    now = utc_now()
    feed: list[dict] = []
    with connect() as db:
        local_rows = db.execute(
            """SELECT id, state, district, crop, title, body, issued_at, valid_until, 'local' AS exchange_source
            FROM advisories WHERE state=? AND district=? AND crop=? AND status='published' AND valid_until>=?
            ORDER BY issued_at DESC""",
            (field["state"], field["district"], field["crop"], now),
        ).fetchall()
        exchange_rows = db.execute(
            """SELECT id, payload_json FROM exchange_receipts
            WHERE target_state=? AND status='accepted' ORDER BY received_at DESC""",
            (field["state"],),
        ).fetchall()
    feed.extend(dict(row) for row in local_rows)
    for receipt in exchange_rows:
        payload = json.loads(receipt["payload_json"])
        if payload.get("target_district") != field["district"] or payload.get("crop") != field["crop"] or payload.get("valid_until", "") < now:
            continue
        feed.append({
            "id": receipt["id"], "state": payload["source_state"], "district": payload["target_district"],
            "crop": payload["crop"], "title": payload["title"], "body": payload["body"],
            "issued_at": payload["issued_at"], "valid_until": payload["valid_until"],
            "exchange_source": f"Shared from {payload['source_state']}",
            "source_district": payload["source_district"],
        })
    return feed


@router.get("/cases/my")
async def my_cases(identity: dict = Depends(current_identity)) -> list[dict]:
    require_farmer(identity)
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM cases WHERE owner_id=? ORDER BY created_at DESC LIMIT 50",
            (identity["actor_id"],),
        ).fetchall()
    return [_case_payload(dict(row)) for row in rows]


@router.post("/cases")
async def create_case(
    field_id: str = Form(...),
    question: str = Form(default=""),
    transcript: str = Form(default=""),
    language: str = Form(default="en"),
    submission_id: str = Form(default=""),
    photo: UploadFile | None = File(default=None),
    identity: dict = Depends(current_identity),
) -> dict:
    require_farmer(identity)
    field = _load_field_for_owner(field_id, identity["actor_id"])
    submission_id = submission_id.strip()
    if submission_id and not re.fullmatch(r"[A-Za-z0-9_-]{12,80}", submission_id):
        raise HTTPException(status_code=422, detail="Invalid submission identifier.")
    if submission_id:
        with connect() as db:
            duplicate = db.execute(
                "SELECT * FROM cases WHERE owner_id=? AND submission_key=?",
                (identity["actor_id"], submission_id),
            ).fetchone()
        if duplicate is not None:
            return _case_payload(dict(duplicate))
    if language not in LANGUAGE_CODES:
        raise HTTPException(status_code=422, detail="Choose Telugu, Hindi, or English.")
    if not question.strip() and (photo is None or not photo.filename):
        raise HTTPException(status_code=422, detail="Add a question or attach a crop photo.")
    normalized_question = question.strip()[:1500]
    if not normalized_question:
        normalized_question = {"te": "ఈ పంట చిత్రాన్ని చూసి సహాయం చేయండి.", "hi": "कृपया इस फसल की तस्वीर देखकर मदद करें।"}.get(language, "Please help me understand this crop image.")
    if len(normalized_question) < 4:
        raise HTTPException(status_code=422, detail="Add a little more detail to your question.")

    image_bytes = None
    image_info = None
    if photo is not None and photo.filename:
        raw = await photo.read(settings.max_image_bytes + 1)
        if len(raw) > settings.max_image_bytes:
            raise HTTPException(status_code=413, detail="Image is larger than the 5 MB limit.")
        if not raw:
            raise HTTPException(status_code=400, detail="The selected image is empty.")
        image_bytes, image_info = _private_image(raw)

    context = await _context_payload(field)
    evidence = list(context["evidence"])
    practices = practice_evidence(field, language)
    evidence.extend(practices)
    if image_info:
        evidence.append({
            "id": PHOTO_EVIDENCE_ID,
            "type": "user_uploaded_image",
            "label": "Farmer-provided crop image",
            "scope": f"User-supplied image for {field['crop']}; not independently verified.",
            "dimensions": {"width": image_info["width"], "height": image_info["height"]},
            "live": False,
        })
    try:
        advisory = await generate_advisory(
            normalized_question, field["crop"], language, evidence,
            image_bytes, image_info["mime_type"] if image_info else None,
        )
    except (ValueError, RuntimeError) as exc:
        # Save the farmer request even when AI fails, without fabricating AI advice.
        from backend.ai_service import demo_abstention, failure_category
        advisory = demo_abstention(language, bool(image_bytes))
        advisory["summary"] = {"en": "AI guidance is unavailable right now. No AI answer was generated. You can contact an officer below.", "hi": "अभी AI सलाह उपलब्ध नहीं है। AI जवाब नहीं बना। नीचे दिए विकल्प से अधिकारी से संपर्क कर सकते हैं।", "te": "ప్రస్తుతం AI సలహా అందుబాటులో లేదు. AI సమాధానం రూపొందించలేదు. కింద ఉన్న ఎంపికతో అధికారిని సంప్రదించవచ్చు."}[language]
        advisory["uncertainty"] = {
            "en": "The provider failed or the answer could not be checked. No diagnosis or treatment was generated.",
            "hi": "सेवा का जवाब उपलब्ध नहीं हुआ या उसकी जाँच नहीं हो सकी। कोई निदान या उपचार नहीं बनाया गया।",
            "te": "సేవ సమాధానం ఇవ్వలేదు లేదా దాన్ని తనిఖీ చేయలేకపోయాం. నిర్ధారణ లేదా చికిత్స సూచించలేదు.",
        }[language]
        advisory["failure_category"] = failure_category(exc)
        advisory["retry_after_seconds"] = getattr(exc, "retry_after_seconds", None)
        advisory["provider"] = "ai-unavailable"
        advisory["answer_basis"] = "unavailable"
    advisory["contact_recommended"] = bool(advisory.get("needs_officer_review") or image_bytes or advisory.get("answer_basis") in {"general", "unavailable"})
    advisory["language"] = language
    manifest = artifact_manifest()
    advisory["metadata"] = {
        "prompt_version": PROMPT_VERSION if advisory.get("live_model_call") else "demo-abstention-v1",
        "data_artifact_version": manifest["artifact_version"],
        "data_source_sha256": manifest["source"]["sha256"],
        "guidance_set_version": "curated-2026-09-v2",
    }
    photo_path = None

    now = utc_now()
    case_id = f"case-{uuid.uuid4().hex[:12]}"
    try:
        with connect() as db:
            db.execute(
                """INSERT INTO cases
                (id, field_id, owner_id, state, district, crop, question, transcript, status,
                 submission_key, provider, model, advisory_json, evidence_json, photo_path, photo_shared,
                 created_at, updated_at, version)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    case_id, field_id, identity["actor_id"], field["state"], field["district"], field["crop"],
                    normalized_question, transcript.strip()[:1500] or None,
                    "guidance_unavailable" if advisory.get("answer_basis") == "unavailable" else "answered", submission_id or None,
                    advisory["provider"], advisory.get("model"), json_dumps(advisory), json_dumps(evidence),
                    photo_path, int(bool(photo_path)), now, now,
                ),
            )
    except Exception:
        if photo_path:
            (settings.upload_dir / photo_path).unlink(missing_ok=True)
        raise
    return _case_payload(_load_case(case_id))


@router.post("/cases/{case_id}/contact-officer")
async def contact_officer(
    case_id: str,
    expected_version: int = Form(..., ge=1),
    name: str = Form(..., min_length=2, max_length=100),
    phone: str = Form(..., min_length=10, max_length=16),
    location: str = Form(..., min_length=2, max_length=180),
    query: str = Form(..., min_length=4, max_length=1500),
    consent: bool = Form(...),
    photo: UploadFile | None = File(default=None),
    identity: dict = Depends(current_identity),
) -> dict:
    require_farmer(identity)
    name, location, query = name.strip(), location.strip(), query.strip()
    phone_digits = re.sub(r"[\s()+-]", "", phone)
    if not consent:
        raise HTTPException(status_code=422, detail="Consent is required to share this request with an officer.")
    if not re.fullmatch(r"(?:91)?[6-9]\d{9}", phone_digits):
        raise HTTPException(status_code=422, detail="Enter a valid Indian mobile number.")
    if len(name) < 2 or len(location) < 2 or len(query) < 4:
        raise HTTPException(status_code=422, detail="Complete the name, location, and question fields.")

    image_bytes = None
    if photo is not None and photo.filename:
        raw = await photo.read(settings.max_image_bytes + 1)
        if len(raw) > settings.max_image_bytes:
            raise HTTPException(status_code=413, detail="Image is larger than the 5 MB limit.")
        if not raw:
            raise HTTPException(status_code=400, detail="The selected image is empty.")
        image_bytes, _ = _private_image(raw)

    photo_path = None
    if image_bytes:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        photo_path = f"{uuid.uuid4().hex}.jpg"
        (settings.upload_dir / photo_path).write_bytes(image_bytes)
    now = utc_now()
    replaced_photo_path = None
    try:
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            record = db.execute("SELECT * FROM cases WHERE id=? AND owner_id=?", (case_id, identity["actor_id"])).fetchone()
            if record is None:
                raise HTTPException(status_code=404, detail="Case not found for this farmer.")
            row = dict(record)
            if row["version"] != expected_version:
                raise HTTPException(status_code=409, detail="This case changed; refresh before contacting an officer.")
            if row.get("contact_requested_at"):
                raise HTTPException(status_code=409, detail="An officer contact request already exists for this case.")
            if row["status"] in {"resolved", "rejected"}:
                raise HTTPException(status_code=409, detail="This case is closed. Submit a new question.")
            replaced_photo_path = row.get("photo_path") if photo_path else None
            db.execute(
                """UPDATE cases SET status='needs_review', contact_name=?, contact_phone=?, contact_location=?,
                contact_query=?, contact_requested_at=?, photo_path=COALESCE(?, photo_path),
                photo_shared=CASE WHEN ? IS NULL THEN photo_shared ELSE 1 END,
                version=version+1, updated_at=? WHERE id=? AND version=?""",
                (name, phone_digits, location, query, now, photo_path, photo_path, now, case_id, expected_version),
            )
            saved = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    except Exception:
        if photo_path:
            (settings.upload_dir / photo_path).unlink(missing_ok=True)
        raise
    if replaced_photo_path:
        (settings.upload_dir / Path(replaced_photo_path).name).unlink(missing_ok=True)
    return _case_payload(dict(saved))


@router.delete("/cases/{case_id}/photo")
async def delete_case_photo(case_id: str, identity: dict = Depends(current_identity)) -> dict:
    row = _load_case(case_id)
    _check_case_access(row, identity)
    path = row.get("photo_path")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE cases SET photo_path=NULL, photo_shared=0, updated_at=?, version=version+1 WHERE id=?",
            (utc_now(), case_id),
        )
    if path:
        (settings.upload_dir / Path(path).name).unlink(missing_ok=True)
    return {"case_id": case_id, "photo_deleted": True}


@router.get("/cases/{case_id}")
async def case_detail(case_id: str, identity: dict = Depends(current_identity)) -> dict:
    row = _load_case(case_id)
    _check_case_access(row, identity)
    return _case_payload(row, include_contact=identity["role"] == "officer")


@router.post("/cases/{case_id}/review-request", include_in_schema=False)
async def request_review(case_id: str, identity: dict = Depends(current_identity)) -> dict:
    require_farmer(identity)
    raise HTTPException(
        status_code=410,
        detail="Use the contact form to share your details and request an officer follow-up.",
    )


@router.post("/cases/{case_id}/reply")
async def farmer_reply(case_id: str, payload: FarmerReplyRequest, identity: dict = Depends(current_identity)) -> dict:
    require_farmer(identity)
    if len(payload.text.strip()) < 4:
        raise HTTPException(status_code=422, detail="Add a little more detail.")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        record = db.execute("SELECT * FROM cases WHERE id=? AND owner_id=?", (case_id, identity["actor_id"])).fetchone()
        if record is None:
            raise HTTPException(status_code=404, detail="Case not found for this farmer.")
        row = dict(record)
        if row["version"] != payload.expected_version or row["status"] != "needs_information":
            raise HTTPException(status_code=409, detail="Refresh this case; it is not currently waiting for more information.")
        now = utc_now()
        db.execute("INSERT INTO case_messages (id, case_id, body, created_at) VALUES (?, ?, ?, ?)", (uuid.uuid4().hex, case_id, payload.text.strip(), now))
        db.execute("UPDATE cases SET status='needs_review', version=version+1, updated_at=? WHERE id=?", (now, case_id))
    return _case_payload(_load_case(case_id))


@router.get("/officer/queue")
async def officer_queue(include_closed: bool = Query(False), identity: dict = Depends(current_identity)) -> list[dict]:
    require_officer(identity)
    with connect() as db:
        rows = db.execute(
            """SELECT * FROM cases WHERE state=? AND
            (status IN ('needs_review','needs_information','approved') OR (? AND status IN ('rejected','resolved')))
            ORDER BY created_at DESC LIMIT 100""", (officer_state(identity), include_closed)
        ).fetchall()
    return [_case_payload(dict(row), include_contact=True) for row in rows]


@router.get("/officer/cases/{case_id}/photo")
async def officer_case_photo(case_id: str, identity: dict = Depends(current_identity)) -> FileResponse:
    require_officer(identity)
    row = _load_case(case_id)
    _check_case_access(row, identity)
    if not row.get("photo_shared") or not row.get("photo_path"):
        raise HTTPException(status_code=404, detail="The farmer did not share a photo for officer review.")
    upload_root = settings.upload_dir.resolve()
    file_path = (upload_root / Path(row["photo_path"]).name).resolve()
    if not file_path.is_relative_to(upload_root) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Private photo is no longer available.")
    return FileResponse(file_path, media_type="image/jpeg", filename="farmer-upload.jpg")


@router.get("/officer/cases/{case_id}/reviews")
async def officer_case_reviews(case_id: str, identity: dict = Depends(current_identity)) -> list[dict]:
    require_officer(identity)
    row = _load_case(case_id)
    _check_case_access(row, identity)
    with connect() as db:
        rows = db.execute(
            "SELECT status, note, ai_decision, created_at, case_version FROM reviews WHERE case_id=? ORDER BY created_at DESC",
            (case_id,),
        ).fetchall()
    return [dict(item) for item in rows]


@router.post("/officer/cases/{case_id}/review")
async def review_case(case_id: str, payload: ReviewRequest, identity: dict = Depends(current_identity)) -> dict:
    require_officer(identity)
    status = payload.status
    now = utc_now()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Case not found.")
        current = dict(row)
        _check_case_access(current, identity)
        if current["version"] != payload.expected_version:
            raise HTTPException(status_code=409, detail="This case changed; reload it before reviewing.")
        if current["status"] in {"rejected", "resolved"}:
            raise HTTPException(status_code=409, detail="This case is closed and cannot be changed.")
        if payload.ai_decision is not None:
            if current["provider"] != "Google Gemini API":
                raise HTTPException(status_code=422, detail="This case has no generated AI response to review.")
            if status != "approved":
                raise HTTPException(status_code=422, detail="An AI review must approve follow-up for this case.")
            if payload.ai_decision == "rejected" and len(payload.note.strip()) < 10:
                raise HTTPException(status_code=422, detail="Write your response before rejecting the AI response (at least 10 characters).")
        next_version = current["version"] + 1
        db.execute(
            "UPDATE cases SET status=?, updated_at=?, version=? WHERE id=? AND version=?",
            (status, now, next_version, case_id, payload.expected_version),
        )
        db.execute(
            "INSERT INTO reviews (id, case_id, officer_id, status, note, ai_decision, created_at, case_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (f"review-{uuid.uuid4().hex[:12]}", case_id, identity["actor_id"], status, payload.note.strip(), payload.ai_decision, now, next_version),
        )
        changed = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    return _case_payload(dict(changed), include_contact=True)


@router.post("/officer/advisories")
async def publish_advisory(payload: PublishAdvisoryRequest, identity: dict = Depends(current_identity)) -> dict:
    require_officer(identity)
    source_case = _load_case(payload.source_case_id)
    _check_case_access(source_case, identity)
    if source_case["status"] != "approved":
        raise HTTPException(status_code=409, detail="Review and approve the source case before publishing.")
    if _sensitive_public_text(payload.title + "\n" + payload.body):
        raise HTTPException(status_code=422, detail="Remove personal identifiers or contact details before publishing.")
    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    issued_at = now_dt.isoformat()
    valid_until = (now_dt + timedelta(days=payload.valid_days)).isoformat()
    advisory_id = f"regional-{uuid.uuid4().hex[:12]}"
    advisory = {
        "id": advisory_id, "state": source_case["state"], "district": source_case["district"],
        "crop": source_case["crop"], "title": payload.title.strip(), "body": payload.body.strip(),
        "issued_at": issued_at, "valid_until": valid_until, "status": "published", "version": 1,
        "source_case_id": source_case["id"],
    }
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        # Check approval in the same transaction as publication and sharing.
        current = db.execute("SELECT * FROM cases WHERE id=?", (source_case["id"],)).fetchone()
        if current is None or current["status"] != "approved":
            raise HTTPException(status_code=409, detail="Review and approve the source case before publishing.")
        db.execute(
            """INSERT INTO advisories
            (id, state, district, crop, title, body, source_case_id, officer_id, issued_at, valid_until, status, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', 1)""",
            (advisory_id, source_case["state"], source_case["district"], source_case["crop"], payload.title.strip(),
             payload.body.strip(), source_case["id"], identity["actor_id"], issued_at, valid_until),
        )
        if advisory["state"] == "Telangana":
            _share_advisory(db, advisory)
    return advisory


@router.get("/officer/advisories")
async def list_regional_advisories(identity: dict = Depends(current_identity)) -> list[dict]:
    require_officer(identity)
    with connect() as db:
        rows = db.execute("SELECT * FROM advisories WHERE state=? ORDER BY issued_at DESC LIMIT 50", (officer_state(identity),)).fetchall()
    return [dict(row) for row in rows]


@router.post("/officer/advisories/{advisory_id}/exchange")
async def exchange_advisory(advisory_id: str, identity: dict = Depends(current_identity)) -> dict:
    require_officer(identity)
    if officer_state(identity) != "Telangana":
        raise HTTPException(status_code=403, detail="This demo export is available to Telangana officers only.")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        advisory_row = db.execute("SELECT * FROM advisories WHERE id=?", (advisory_id,)).fetchone()
        if advisory_row is None:
            raise HTTPException(status_code=404, detail="Advisory not found.")
        return _share_advisory(db, dict(advisory_row))


def _share_advisory(db: sqlite3.Connection, advisory: dict) -> dict:
    """Persist the existing PII-free regional contract atomically with publication."""
    target = STATE_ADAPTERS["Andhra Pradesh"]
    if advisory["state"] != "Telangana" or advisory["status"] != "published":
        raise HTTPException(status_code=409, detail="Only a published Telangana advisory can be shared.")
    if advisory["valid_until"] < utc_now():
        raise HTTPException(status_code=409, detail="This advisory has expired.")
    if _sensitive_public_text(advisory["title"] + "\n" + advisory["body"]):
        raise HTTPException(status_code=422, detail="Remove personal identifiers or contact details before sharing.")
    source_case = dict(db.execute("SELECT * FROM cases WHERE id=?", (advisory["source_case_id"],)).fetchone())
    evidence_rows = json.loads(source_case["evidence_json"])
    safe_evidence_ids = [item["id"] for item in evidence_rows if item.get("id") != PHOTO_EVIDENCE_ID]
    contract = build_regional_contract(advisory, target, safe_evidence_ids)
    payload_json = contract.model_dump_json()
    dedupe_key = f"{advisory['id']}:v{advisory['version']}:{target.state}:{target.receiving_district}"
    existing = db.execute("SELECT * FROM exchange_receipts WHERE dedupe_key=?", (dedupe_key,)).fetchone()
    if existing:
        return {"receipt_id": existing["id"], "status": existing["status"], "duplicate": True, "payload": json.loads(existing["payload_json"])}
    receipt_id = f"receipt-{uuid.uuid4().hex[:12]}"
    db.execute(
        """INSERT INTO exchange_receipts
        (id, advisory_id, source_state, target_state, contract_version, dedupe_key, payload_json, received_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'accepted')""",
        (receipt_id, advisory["id"], "Telangana", target.state, "1.0", dedupe_key, payload_json, utc_now()),
    )
    return {"receipt_id": receipt_id, "status": "accepted", "duplicate": False, "payload": json.loads(payload_json)}


@router.get("/officer/exchanges")
async def exchange_receipts(identity: dict = Depends(current_identity)) -> list[dict]:
    require_officer(identity)
    with connect() as db:
        state = officer_state(identity)
        rows = db.execute("SELECT * FROM exchange_receipts WHERE source_state=? OR target_state=? ORDER BY received_at DESC LIMIT 50", (state, state)).fetchall()
    return [
        {**dict(row), "payload": json.loads(row["payload_json"])} for row in rows
    ]
