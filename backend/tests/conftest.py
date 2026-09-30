from dataclasses import replace

import pytest

import backend.weather_service as weather


@pytest.fixture(autouse=True)
def isolated_weather(monkeypatch):
    """Never depend on workstation keys/network; provider tests opt into mocks."""
    monkeypatch.setattr(weather, "settings", replace(weather.settings, openweather_api_key="", enable_no_key_weather=False))
    weather._CACHE.clear()
    yield
    weather._CACHE.clear()
