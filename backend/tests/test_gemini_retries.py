import asyncio
import json
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend.config import settings as base_settings
import backend.ai_service as ai_service


def test_gemini_deadline_timeout_raises_timeout_error(monkeypatch):
    monkeypatch.setattr(ai_service, "settings", replace(base_settings, gemini_api_key="test-key"))

    class HangingModels:
        async def generate_content(self, **kwargs):
            await asyncio.sleep(0.01)
            raise TimeoutError("Simulated socket timeout")

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

        def __init__(self, api_key, **kwargs):
            self.aio = self
            self.models = HangingModels()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", FakeClient)

    # Calling with an already expired or very short deadline should abort with timeout
    with pytest.raises(RuntimeError, match="Gemini timeout"):
        # We can pass an expired deadline directly into _generate_sync
        asyncio.run(ai_service.generate_advisory(
            "Test question", "Rice", "en", [], None, None
        ))


def test_gemini_retries_aborts_when_deadline_exceeded(monkeypatch):
    monkeypatch.setattr(ai_service, "settings", replace(base_settings, gemini_api_key="test-key"))

    # Test direct _generate_sync with an already passed deadline
    with pytest.raises(TimeoutError, match="Gemini request deadline reached"):
        asyncio.run(ai_service._generate_async(
            "Test question", "Rice", "en", [], None, None, deadline=time.monotonic() - 1.0
        ))


def test_gemini_quota_cooldown_and_model_fallback(monkeypatch):
    ai_service._quota_cooldown.clear()
    ai_service._model_cooldown.clear()
    monkeypatch.setattr(ai_service, "settings", replace(
        base_settings, gemini_api_key="test-key", gemini_model="gemini-3.5-flash-lite"
    ))

    calls = []

    class MultiModelMock:
        async def generate_content(self, model, **kwargs):
            calls.append(model)
            if model == "gemini-3.5-flash-lite":
                # Raise 429 quota error
                err = Exception("429 ResourceExhausted: quota exceeded")
                err.code = 429
                raise err
            # Fallback model succeeds
            return SimpleNamespace(text=json.dumps({
                "summary": f"Success from {model}",
                "summary_source_ids": [],
                "possible_causes": [],
                "uncertainty": "Tested fallback.",
                "needs_officer_review": True,
                "answer_basis": "general",
            }))

    class MultiModelClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

        def __init__(self, api_key, **kwargs):
            self.aio = self
            self.models = MultiModelMock()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", MultiModelClient)

    result = asyncio.run(ai_service.generate_advisory(
        "Leaf question", "Rice", "en", [], None, None
    ))

    assert result["live_model_call"] is True
    assert calls == ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
    assert result["model"] == "gemini-3.8-flash"
    # Verify the quota-limited model is cooled down.
    assert "gemini-3.5-flash-lite" in ai_service._quota_cooldown
    assert ai_service._quota_cooldown["gemini-3.5-flash-lite"] > time.monotonic()


def test_gemini_does_not_retry_other_models_for_invalid_key(monkeypatch):
    ai_service._quota_cooldown.clear()
    ai_service._model_cooldown.clear()
    monkeypatch.setattr(ai_service, "settings", replace(
        base_settings, gemini_api_key="test-key", gemini_model="gemini-3.5-flash-lite"
    ))
    calls = []

    class InvalidKeyModels:
        async def generate_content(self, model, **kwargs):
            calls.append(model)
            error = Exception("401 API key invalid")
            error.code = 401
            raise error

    class InvalidKeyClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

        def __init__(self, api_key, **kwargs):
            self.aio = self
            self.models = InvalidKeyModels()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", InvalidKeyClient)

    with pytest.raises(ai_service.ProviderFailure, match="auth"):
        asyncio.run(ai_service._generate_async(
            "Test question", "Rice", "en", [], None, None,
            deadline=time.monotonic() + 20,
        ))

    assert calls == ["gemini-3.5-flash-lite"]


def test_evidence_brief_includes_soil_and_satellite_measurements(monkeypatch):
    captured_prompts = []

    class CaptureModels:
        async def generate_content(self, contents, **kwargs):
            captured_prompts.append(contents[0])
            return SimpleNamespace(text=json.dumps({
                "summary": "Soil and satellite evidence received.",
                "summary_source_ids": ["weather-live"],
                "possible_causes": [],
                "uncertainty": "Regional values only.",
                "needs_officer_review": True,
                "answer_basis": "general",
            }))

    class CaptureClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

        def __init__(self, api_key, **kwargs):
            self.aio = self
            self.models = CaptureModels()

    import google.genai
    monkeypatch.setattr(google.genai, "Client", CaptureClient)
    monkeypatch.setattr(ai_service, "settings", replace(base_settings, gemini_api_key="test-key"))

    evidence = [
        {
            "id": "soil-nalgonda-shc-2024",
            "type": "recorded_soil_observation",
            "label": "District Soil Benchmark",
            "observed_at": "2024-05-10",
            "values": {"ph": 7.2, "available_nitrogen_kg_ha": 210.0},
            "warning": "District-level benchmark.",
            "report_id": "SHC-TS-NAL-2024-C2",
            "verification_status": "unverified_demo_fixture",
        },
        {
            "id": "satellite-nalgonda-s2-2026-08",
            "type": "recorded_satellite_observation",
            "label": "Satellite Vegetation Index",
            "observed_at": "2026-08-28T05:15:00Z",
            "values": {"mean_ndvi": 0.64},
            "observation_vs_inference": "Observation: NDVI 0.64. Inference: Typical vigor.",
            "scene_id": "S2B_MSIL2A_20260828T051519",
            "verification_status": "unverified_demo_fixture",
            "warning": "Canopy reflectance aggregate.",
        },
        {
            "id": "hist-context",
            "type": "historical_dataset_summary",
            "label": "Historical summary",
            "values": {"undocumented_temp": 32},
            "warning": "Undocumented units.",
        }
        ,{"id": "weather-live", "type": "live_weather_observation", "label": "Weather", "values": {"temperature_c": 27}}
    ]

    result = asyncio.run(ai_service.generate_advisory(
        "How is the soil and vegetation?", "Rice", "en", evidence, None, None
    ))

    assert result["live_model_call"] is True
    prompt_str = captured_prompts[0]
    # Unverified demo soil/satellite values and their prose are excluded.
    assert '"ph": 7.2' not in prompt_str
    assert '"available_nitrogen_kg_ha": 210.0' not in prompt_str
    assert '"SHC-TS-NAL-2024-C2"' not in prompt_str
    assert '"mean_ndvi": 0.64' not in prompt_str
    assert '"S2B_MSIL2A_20260828T051519"' not in prompt_str
    assert 'unverified_demo_fixture' not in prompt_str
    assert '"temperature_c": 27' in prompt_str

    # Historical undocumented values must NOT be passed into prompt
    assert '"undocumented_temp": 32' not in prompt_str
