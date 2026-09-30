import os
import subprocess
import sys

import pytest

from backend.config import deployment_secret


def test_production_requires_stable_secret_and_explicit_demo(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('SESSION_SECRET', '')
    with pytest.raises(RuntimeError, match='SESSION_SECRET'):
        deployment_secret()
    monkeypatch.setenv('SESSION_SECRET', 's' * 32)
    monkeypatch.delenv('DEMO_MODE', raising=False)
    with pytest.raises(RuntimeError, match='DEMO_MODE'):
        deployment_secret()
    monkeypatch.setenv('DEMO_MODE', 'true')
    assert deployment_secret() == 's' * 32


def test_production_fails_before_serving_requests():
    env = dict(os.environ, APP_ENV='production', SESSION_SECRET='', DEMO_MODE='true')
    result = subprocess.run([sys.executable, '-c', 'import backend.main'], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Production requires SESSION_SECRET' in result.stderr
