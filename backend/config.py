from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_local_env() -> None:
    """Read a small .env file without making dotenv a runtime dependency."""
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_local_env()


def configured_path(variable: str, default: str) -> Path:
    path = Path(os.getenv(variable, default))
    return path if path.is_absolute() else ROOT / path


def deployment_secret() -> str:
    secret = os.getenv("SESSION_SECRET", "")
    if secret == "replace-with-a-random-local-value":
        secret = ""
    if os.getenv("APP_ENV", "development") == "production":
        if len(secret) < 32:
            raise RuntimeError("Production requires SESSION_SECRET with at least 32 characters.")
        if os.getenv("DEMO_MODE", "").casefold() not in {"true", "false"}:
            raise RuntimeError("Production requires an explicit DEMO_MODE=true or false.")
    return secret or secrets.token_urlsafe(32)


@dataclass(frozen=True)
class Settings:
    demo_mode: bool
    session_secret: str
    gemini_api_key: str
    gemini_model: str
    openweather_api_key: str
    enable_recorded_observations: bool
    database_path: Path
    upload_dir: Path
    max_image_bytes: int
    port: int
    enable_no_key_weather: bool = True


settings = Settings(
    demo_mode=os.getenv("DEMO_MODE", "true").casefold() == "true",
    session_secret=deployment_secret(),
    gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
    gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    openweather_api_key=os.getenv("OPENWEATHER_API_KEY", ""),
    enable_recorded_observations=os.getenv("ENABLE_RECORDED_OBSERVATIONS", "true").casefold() == "true",
    database_path=configured_path("DATABASE_PATH", "backend/data/runtime/agrisathi.sqlite3"),
    upload_dir=configured_path("UPLOAD_DIR", "backend/data/uploads"),
    max_image_bytes=max(1024, int(os.getenv("MAX_IMAGE_BYTES", str(5 * 1024 * 1024)))),
    port=int(os.getenv("PORT", "8000")),
    enable_no_key_weather=os.getenv("ENABLE_NO_KEY_WEATHER", "true").casefold() == "true",
)
