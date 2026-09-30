from __future__ import annotations

import time
import math
from datetime import datetime, timezone

import httpx

from backend.config import settings

_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_CITY_BY_DISTRICT = {"Nalgonda": "Nalgonda", "Khammam": "Khammam", "Krishna": "Machilipatnam"}
_REFERENCE_POINTS = {"Nalgonda": (17.0, 79.3), "Khammam": (17.25, 80.12), "Krishna": (16.3, 81.05)}


async def current_weather(district: str) -> dict:
    estimated = not settings.openweather_api_key
    if estimated and not settings.enable_no_key_weather:
        return {
            "status": "unavailable",
            "reason": "No weather provider key is configured.",
            "data_type": "missing",
            "live": False,
        }
    cache_key = (district, "Open-Meteo" if estimated else "OpenWeather")
    cached = _CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < 30 * 60:
        return cached[1]

    city = _CITY_BY_DISTRICT.get(district)
    if not city:
        return {"status": "unavailable", "reason": "No configured reference location for this district.", "data_type": "missing", "live": False}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if estimated:
                latitude, longitude = _REFERENCE_POINTS[district]
                response = await client.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": latitude, "longitude": longitude,
                    "current": "temperature_2m,relative_humidity_2m",
                    "timezone": "UTC", "timeformat": "unixtime", "forecast_days": 1,
                })
            else:
                response = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": f"{city},IN", "appid": settings.openweather_api_key, "units": "metric"},
                )
            response.raise_for_status()
            payload = response.json()
        if estimated:
            current = payload["current"]
            temperature, humidity = current["temperature_2m"], current["relative_humidity_2m"]
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                   for value in (temperature, humidity)) or not 0 <= humidity <= 100:
                raise ValueError("Invalid model estimate")
            result = {
                "status": "available", "data_type": "live_provider_estimate",
                "provider": "Open-Meteo", "reference_location": f"{district} reference point",
                "spatial_scope": "Weather-model grid at a district reference point; not a station observation or field measurement.",
                "observed_at": datetime.fromtimestamp(current["time"], tz=timezone.utc).isoformat(),
                "temperature_c": temperature, "atmospheric_humidity_percent": humidity,
                "rainfall_last_hour_mm": None, "cloud_cover_percent": None,
                "rain_probability": None, "soil_moisture": None, "live": True,
            }
            _CACHE[cache_key] = (time.monotonic(), result)
            return result
        observed_at = datetime.fromtimestamp(payload["dt"], tz=timezone.utc).isoformat()
        rain = payload.get("rain", {})
        result = {
            "status": "available",
            "data_type": "live_provider_observation",
            "provider": "OpenWeather",
            "reference_location": payload.get("name", city),
            "spatial_scope": "Named town/reference point; not the farmer's exact field.",
            "observed_at": observed_at,
            "temperature_c": payload.get("main", {}).get("temp"),
            "atmospheric_humidity_percent": payload.get("main", {}).get("humidity"),
            "rainfall_last_hour_mm": rain.get("1h"),
            "cloud_cover_percent": payload.get("clouds", {}).get("all"),
            "rain_probability": None,
            "soil_moisture": None,
            "live": True,
        }
        _CACHE[cache_key] = (time.monotonic(), result)
        return result
    except (httpx.HTTPError, KeyError, TypeError, ValueError, OverflowError):
        return {
            "status": "unavailable",
            "reason": "The weather provider request failed; no historical values were substituted.",
            "data_type": "missing",
            "live": False,
        }
