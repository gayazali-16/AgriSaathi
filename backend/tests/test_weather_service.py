import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx

from backend.config import settings as base_settings
import backend.weather_service as weather_service


def test_live_weather_keeps_cloud_cover_rain_and_soil_semantics_separate(monkeypatch):
    observed = datetime(2026, 9, 23, 7, tzinfo=timezone.utc)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "name": "Nalgonda",
                "dt": int(observed.timestamp()),
                "main": {"temp": 29.5, "humidity": 78},
                "clouds": {"all": 91},
                "rain": {"1h": 2.4},
            }

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, params):
            assert params["q"] == "Nalgonda,IN"
            return FakeResponse()

    monkeypatch.setattr(weather_service, "settings", replace(base_settings, openweather_api_key="test-key"))
    monkeypatch.setattr(weather_service.httpx, "AsyncClient", FakeClient)
    weather_service._CACHE.clear()
    assert weather_service._CITY_BY_DISTRICT["Krishna"] == "Machilipatnam"
    result = asyncio.run(weather_service.current_weather("Nalgonda"))
    assert result["temperature_c"] == 29.5
    assert result["atmospheric_humidity_percent"] == 78
    assert result["cloud_cover_percent"] == 91
    assert result["rainfall_last_hour_mm"] == 2.4
    assert result["rain_probability"] is None
    assert result["soil_moisture"] is None
    assert "not the farmer's exact field" in result["spatial_scope"]
    weather_service._CACHE.clear()


def test_missing_key_and_provider_failure_never_substitute_historical_values(monkeypatch):
    weather_service._CACHE.clear()
    monkeypatch.setattr(weather_service, "settings", replace(base_settings, openweather_api_key="", enable_no_key_weather=False))
    absent = asyncio.run(weather_service.current_weather("Nalgonda"))
    assert absent["status"] == "unavailable"
    assert absent["data_type"] == "missing"
    assert absent["live"] is False

    class FailingClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            raise httpx.ReadTimeout("test timeout")

    monkeypatch.setattr(weather_service, "settings", replace(base_settings, openweather_api_key="test-key"))
    monkeypatch.setattr(weather_service.httpx, "AsyncClient", FailingClient)
    failed = asyncio.run(weather_service.current_weather("Nalgonda"))
    assert failed["status"] == "unavailable"
    assert failed["live"] is False
    assert "no historical values were substituted" in failed["reason"]


def test_no_key_model_estimate_provenance_cache_and_failure(monkeypatch):
    calls = []
    current = {"time": 1790769600, "temperature_2m": 28.1, "relative_humidity_2m": 70}
    class Client:
        def __init__(self, timeout):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, params):
            calls.append((url, params))
            return httpx.Response(200, json={"current": current}, request=httpx.Request("GET", url))
    monkeypatch.setattr(weather_service, "settings", replace(base_settings, openweather_api_key="", enable_no_key_weather=True))
    monkeypatch.setattr(weather_service.httpx, "AsyncClient", Client)
    result = asyncio.run(weather_service.current_weather("Nalgonda"))
    assert result["provider"] == "Open-Meteo"
    assert result["data_type"] == "live_provider_estimate"
    assert "not a station observation" in result["spatial_scope"]
    assert result["rainfall_last_hour_mm"] is None and result["soil_moisture"] is None
    assert "appid" not in calls[0][1] and calls[0][1]["latitude"] == 17.0
    assert asyncio.run(weather_service.current_weather("Nalgonda")) == result
    assert len(calls) == 1
    weather_service._CACHE.clear()
    current["temperature_2m"] = None
    assert asyncio.run(weather_service.current_weather("Nalgonda"))["status"] == "unavailable"
    assert not weather_service._CACHE
    current["temperature_2m"] = 28.1
    assert asyncio.run(weather_service.current_weather("Nalgonda"))["status"] == "available"
    assert len(calls) == 3
