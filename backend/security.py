from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException, Request

from backend.config import settings

COOKIE_NAME = "agrisathi_session"
OFFICER_IDENTITIES = {"officer-demo": "Telangana", "officer-demo-ap": "Andhra Pradesh"}

# Public demonstration credentials, usable only while DEMO_MODE is enabled.
DEMO_ACCOUNTS = {
    "ramesh": ("farmer", "farmer-nalgonda-1"),
    "suresh": ("farmer", "farmer-nalgonda-2"),
    "anil": ("farmer", "farmer-khammam-1"),
    "lakshmi": ("farmer", "farmer-krishna-1"),
    "rajesh": ("officer", "officer-demo"),
    "priya": ("officer", "officer-demo-ap"),
}


def demo_login(username: str, password: str) -> tuple[str, str]:
    account = DEMO_ACCOUNTS.get(username.strip().casefold())
    if not hmac.compare_digest(password.encode("utf-8"), b"123") or account is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    return account


def officer_state(identity: dict) -> str:
    require_officer(identity)
    state = OFFICER_IDENTITIES.get(identity.get("actor_id"))
    if not state:
        raise HTTPException(status_code=403, detail="Unknown officer scope.")
    return state
FARMER_IDENTITIES = {
    "farmer-nalgonda-1",
    "farmer-nalgonda-2",
    "farmer-khammam-1",
    "farmer-krishna-1",
}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def issue_session(role: str, actor_id: str) -> str:
    payload = json.dumps(
        {"role": role, "actor_id": actor_id, "issued_at": int(time.time())},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    body = _b64(payload)
    signature = hmac.new(settings.session_secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def verify_session(token: str) -> dict | None:
    try:
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(settings.session_secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode("utf-8"))
        if int(time.time()) - int(payload["issued_at"]) > 12 * 60 * 60:
            return None
        if payload.get("role") not in {"farmer", "officer"}:
            return None
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def current_identity(request: Request) -> dict:
    if not settings.demo_mode:
        raise HTTPException(status_code=503, detail="A production identity provider is not configured.")
    token = request.cookies.get(COOKIE_NAME, "")
    identity = verify_session(token)
    if identity is None:
        raise HTTPException(status_code=401, detail="Select a local demo identity to continue.")
    return identity


def require_farmer(identity: dict) -> dict:
    if identity.get("role") != "farmer":
        raise HTTPException(status_code=403, detail="Farmer access is required for this action.")
    return identity


def require_officer(identity: dict) -> dict:
    if identity.get("role") != "officer":
        raise HTTPException(status_code=403, detail="Officer access is required for this action.")
    return identity
