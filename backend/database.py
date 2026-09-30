from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from backend.config import settings

DEMO_FIELDS = [
    {"id": "field-nalgonda-rice-1", "owner_id": "farmer-nalgonda-1", "state": "Telangana", "district": "Nalgonda", "crop": "Rice", "season": "Kharif", "stage": "Vegetative", "spatial_scope": "District only; sample field profile"},
    {"id": "field-nalgonda-rice-2", "owner_id": "farmer-nalgonda-2", "state": "Telangana", "district": "Nalgonda", "crop": "Rice", "season": "Kharif", "stage": "Vegetative", "spatial_scope": "District only; sample field profile"},
    {"id": "field-khammam-maize-1", "owner_id": "farmer-khammam-1", "state": "Telangana", "district": "Khammam", "crop": "Maize", "season": "Kharif", "stage": "Vegetative", "spatial_scope": "District only; sample field profile"},
    {"id": "field-krishna-rice-1", "owner_id": "farmer-krishna-1", "state": "Andhra Pradesh", "district": "Krishna", "crop": "Rice", "season": "Kharif", "stage": "Vegetative", "spatial_scope": "District only; sample field profile"},
    {"id": "field-krishna-second-maize-1", "owner_id": "farmer-krishna-1", "state": "Andhra Pradesh", "district": "Krishna", "crop": "Maize", "season": "Kharif", "stage": "Vegetative", "spatial_scope": "District only; sample field profile"},
]


def connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_database() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS fields (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, state TEXT NOT NULL,
                district TEXT NOT NULL, crop TEXT NOT NULL, season TEXT NOT NULL,
                stage TEXT NOT NULL, spatial_scope TEXT NOT NULL,
                demo_profile INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY, field_id TEXT NOT NULL REFERENCES fields(id),
                owner_id TEXT NOT NULL, state TEXT NOT NULL, district TEXT NOT NULL,
                crop TEXT NOT NULL, question TEXT NOT NULL, transcript TEXT,
                submission_key TEXT UNIQUE,
                status TEXT NOT NULL, provider TEXT NOT NULL, model TEXT,
                advisory_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
                photo_path TEXT, photo_shared INTEGER NOT NULL DEFAULT 0,
                contact_name TEXT, contact_phone TEXT, contact_location TEXT,
                contact_query TEXT, contact_requested_at TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS cases_owner_created ON cases(owner_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS cases_status_created ON cases(status, created_at DESC);
            CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
                officer_id TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL,
                created_at TEXT NOT NULL, case_version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS case_messages (
                id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
                body TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS advisories (
                id TEXT PRIMARY KEY, state TEXT NOT NULL, district TEXT NOT NULL,
                crop TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
                source_case_id TEXT NOT NULL REFERENCES cases(id), officer_id TEXT NOT NULL,
                issued_at TEXT NOT NULL, valid_until TEXT NOT NULL,
                status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS advisories_scope ON advisories(state, district, crop, status, valid_until);
            CREATE TABLE IF NOT EXISTS exchange_receipts (
                id TEXT PRIMARY KEY, advisory_id TEXT NOT NULL REFERENCES advisories(id),
                source_state TEXT NOT NULL, target_state TEXT NOT NULL,
                contract_version TEXT NOT NULL, dedupe_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL, received_at TEXT NOT NULL, status TEXT NOT NULL
            );
            """
        )
        existing_columns = {row["name"] for row in db.execute("PRAGMA table_info(cases)")}
        review_columns = {row["name"] for row in db.execute("PRAGMA table_info(reviews)")}
        if "ai_decision" not in review_columns:
            db.execute("ALTER TABLE reviews ADD COLUMN ai_decision TEXT")
        for name, sql_type in (
            ("contact_name", "TEXT"),
            ("contact_phone", "TEXT"),
            ("contact_location", "TEXT"),
            ("contact_query", "TEXT"),
            ("contact_requested_at", "TEXT"),
        ):
            if name not in existing_columns:
                db.execute(f"ALTER TABLE cases ADD COLUMN {name} {sql_type}")
        db.executemany(
            """INSERT OR IGNORE INTO fields
            (id, owner_id, state, district, crop, season, stage, spatial_scope, demo_profile)
            VALUES (:id, :owner_id, :state, :district, :crop, :season, :stage, :spatial_scope, 1)""",
            DEMO_FIELDS,
        )


def row_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
