import asyncio
import json
import time
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from backend import ai_service as ai
from backend.config import settings


def install_client(monkeypatch, handler):
    import google.genai

    class Client:
        def __init__(self, **kwargs):
            self.aio = self
            self.models = SimpleNamespace(generate_content=handler)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(google.genai, 'Client', Client)
    monkeypatch.setattr(ai, 'settings', replace(settings, gemini_api_key='private-test-key'))
    ai._quota_cooldown.clear()
    ai._model_cooldown.clear()


def valid():
    return SimpleNamespace(text=json.dumps(dict(summary='Observe the leaves.', uncertainty='No field inspection.', answer_basis='general')))


@pytest.mark.parametrize('status,category', [(429, 'quota'), (401, 'auth'), (403, 'auth'), (404, 'model'), (400, 'schema'), (503, 'network'), (504, 'timeout')])
def test_categories(status, category):
    error = Exception('provider error')
    error.code = status
    assert ai.failure_category(error) == category
    assert ai.failure_category(httpx.ConnectError('offline')) == 'network'


def test_404_uses_distinct_fallback_and_logs_redacted_provider_message(monkeypatch, caplog):
    calls = []

    async def handler(model, **kwargs):
        calls.append(model)
        if len(calls) == 1:
            error = Exception('models/primary not found; key=private-test-key')
            error.code = 404
            raise error
        assert kwargs['config'].max_output_tokens == 4096
        return valid()

    install_client(monkeypatch, handler)
    result = asyncio.run(ai.generate_advisory('Yellow leaves', 'Rice', 'en', [], None, None))
    assert len(calls) == 2 and calls[0] != calls[1]
    assert result['live_model_call']
    assert 'not found' in caplog.text and 'private-test-key' not in caplog.text


def test_one_json_repair_then_stop(monkeypatch):
    calls = []

    async def handler(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text='{broken')

    install_client(monkeypatch, handler)
    with pytest.raises(ai.ProviderFailure) as error:
        asyncio.run(ai.generate_advisory('Yellow leaves', 'Rice', 'en', [], None, None))
    assert error.value.category == 'schema'
    assert len(calls) == 2
    assert 'within its length limit' in calls[1]['contents'][-1]


def test_all_models_cooling_down_does_not_call_provider(monkeypatch):
    async def handler(**kwargs):
        pytest.fail('quota cooldown must suppress requests')

    install_client(monkeypatch, handler)
    for model in [settings.gemini_model, *ai.GEMINI_FALLBACK_MODELS]:
        ai._quota_cooldown[model] = time.monotonic() + 250
    try:
        with pytest.raises(ai.ProviderFailure) as error:
            asyncio.run(ai.generate_advisory('Yellow leaves', 'Rice', 'en', [], None, None))
        assert error.value.category == 'quota'
        assert 249 <= error.value.retry_after_seconds <= 250
    finally:
        ai._quota_cooldown.clear()
    ai._model_cooldown.clear()


def test_deadline_cancels_inflight_request(monkeypatch):
    cancelled = []

    async def handler(**kwargs):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    install_client(monkeypatch, handler)
    # Allow the per-attempt budget check; make the outer deadline expire quickly.
    original = ai._generate_async
    async def long_budget(*args):
        return await original(*args[:-1], time.monotonic() + 10)
    monkeypatch.setattr(ai, '_generate_async', long_budget)
    monkeypatch.setattr(ai, 'REQUEST_TIMEOUT_SECONDS', 0.03)
    with pytest.raises(ai.ProviderFailure) as error:
        asyncio.run(ai.generate_advisory('Yellow leaves', 'Rice', 'en', [], None, None))
    assert error.value.category == 'timeout'
    assert cancelled == [True]


def test_quota_retry_hint_and_primary_error_survive_fallback_404(monkeypatch):
    calls = []
    async def handler(model, **kwargs):
        calls.append(model)
        error = Exception('Please retry in 55.28s.' if model == settings.gemini_model else 'model unavailable')
        error.code = 429 if model == settings.gemini_model else 404
        raise error
    install_client(monkeypatch, handler)
    with pytest.raises(ai.ProviderFailure) as error:
        asyncio.run(ai.generate_advisory('Yellow leaves', 'Rice', 'en', [], None, None))
    assert error.value.category == 'quota'
    assert 54 <= error.value.retry_after_seconds <= 56
    before = len(calls)
    with pytest.raises(ai.ProviderFailure) as error:
        asyncio.run(ai.generate_advisory('Yellow leaves', 'Rice', 'en', [], None, None))
    assert len(calls) == before
    assert error.value.category == 'quota'
    ai._quota_cooldown.clear()
    ai._model_cooldown.clear()
