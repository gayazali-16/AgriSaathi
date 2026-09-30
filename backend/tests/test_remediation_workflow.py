from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.ai_service import ProviderFailure
from backend.config import settings
from backend.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    import backend.config as config
    import backend.api as api
    import backend.database as database
    import backend.security as security
    import backend.weather_service as weather
    import backend.ai_service as ai
    configured = replace(settings, database_path=tmp_path / 'cases.sqlite3', upload_dir=tmp_path / 'photos',
                         gemini_api_key='', enable_no_key_weather=False, openweather_api_key='', demo_mode=True)
    for module in [config, api, database, security, weather, ai]:
        monkeypatch.setattr(module, 'settings', configured)
    with TestClient(create_app()) as session:
        session.post('/api/v1/session', json={'username': 'ramesh', 'password': '123'})
        yield session


def test_failure_category_persisted_without_provider_message(client, monkeypatch):
    import backend.api as api
    async def fail(*args):
        raise ProviderFailure('quota', 250)
    monkeypatch.setattr(api, 'generate_advisory', fail)
    saved = client.post('/api/v1/cases', data={'field_id': 'field-nalgonda-rice-1', 'question': 'What should I check?', 'language': 'en'}).json()
    assert saved['status'] == 'guidance_unavailable'
    assert saved['advisory']['failure_category'] == 'quota'
    assert saved['advisory']['retry_after_seconds'] == 250
    assert not saved['advisory']['live_model_call']
    assert client.get('/api/v1/cases/my').json()[0]['advisory']['failure_category'] == 'quota'


def test_weather_estimate_evidence_never_claims_station_or_field_observation(client, monkeypatch):
    import backend.api as api
    async def weather(district):
        return {'status': 'available', 'data_type': 'live_provider_estimate', 'provider': 'Open-Meteo',
                'observed_at': '2026-09-30T12:00:00+00:00', 'spatial_scope': 'District model grid',
                'temperature_c': 28, 'atmospheric_humidity_percent': 70,
                'rainfall_last_hour_mm': None, 'cloud_cover_percent': None}
    monkeypatch.setattr(api, 'current_weather', weather)
    context = client.get('/api/v1/fields/field-nalgonda-rice-1/context').json()
    item = next(item for item in context['evidence'] if item['type'] == 'live_weather_estimate')
    assert item['verification_status'] == 'verified_public_estimate'
    assert item['source_url'] == 'https://open-meteo.com/en/docs'
    assert 'not a station observation' in item['warning']


def test_health_reports_storage_failure_and_production_cookie_is_secure(client, monkeypatch):
    import sqlite3
    import backend.api as api
    monkeypatch.setenv('APP_ENV', 'production')
    response = client.post('/api/v1/session', json={'username': 'ramesh', 'password': '123'})
    assert 'Secure' in response.headers['set-cookie']
    def broken():
        raise sqlite3.OperationalError('private path')
    monkeypatch.setattr(api, 'connect', broken)
    response = client.get('/api/v1/health')
    assert response.status_code == 503
    assert 'private path' not in response.text


@pytest.mark.parametrize('status', ['resolved', 'rejected'])
def test_closed_history_preserves_role_state_and_version_guards(client, status):
    saved = client.post('/api/v1/cases', data={'field_id': 'field-nalgonda-rice-1', 'question': 'What should I check?', 'language': 'en'}).json()
    case_id = saved['id']
    response = client.post(f'/api/v1/cases/{case_id}/contact-officer', data={
        'expected_version': 1, 'name': 'Synthetic Farmer', 'phone': '9876543210',
        'location': 'Nalgonda, Telangana', 'query': 'What should I check?', 'consent': 'true'})
    assert response.status_code == 200
    assert client.get('/api/v1/officer/queue?include_closed=true').status_code == 403
    client.post('/api/v1/session', json={'username': 'rajesh', 'password': '123'})
    closed = client.post(f'/api/v1/officer/cases/{case_id}/review', json={
        'expected_version': 2, 'status': status, 'note': 'Synthetic closure note.'})
    assert closed.status_code == 200
    assert client.get('/api/v1/officer/queue').json() == []
    assert client.get('/api/v1/officer/queue?include_closed=true').json()[0]['id'] == case_id
    assert client.get(f'/api/v1/officer/cases/{case_id}/reviews').json()[0]['note'] == 'Synthetic closure note.'
    assert client.post(f'/api/v1/officer/cases/{case_id}/review', json={
        'expected_version': 3, 'status': 'approved'}).status_code == 409
    client.post('/api/v1/session', json={'username': 'priya', 'password': '123'})
    assert client.get('/api/v1/officer/queue?include_closed=true').json() == []


def test_source_attribution_comes_from_state_adapter():
    from backend.exchange import STATE_ADAPTERS, build_regional_contract
    contract = build_regional_contract(dict(id='test', version=1, state='Telangana', district='Khammam',
        crop='Maize', title='Regional maize observations', body='Observe plants before taking action.',
        issued_at='2026-09-30', valid_until='2026-10-10'), STATE_ADAPTERS['Andhra Pradesh'], ['user-photo', 'reference'])
    assert contract.review_attribution == f'{contract.source_state} extension officer'
    assert contract.evidence_ids == ['reference']


def test_demo_credentials_are_checked_and_roles_are_server_selected(client, monkeypatch):
    import backend.api as api
    client.delete('/api/v1/session')
    for credentials in ({'username': 'rajesh', 'password': 'wrong'}, {'username': 'unknown', 'password': '123'}):
        assert client.post('/api/v1/session', json=credentials).status_code == 401
        assert not client.get('/api/v1/session').json()['authenticated']
    assert client.post('/api/v1/session', json={'role': 'officer', 'identity': 'officer-demo'}).status_code == 422
    signed_in = client.post('/api/v1/session', json={'username': ' RAMESH ', 'password': '123', 'role': 'officer'}).json()
    assert signed_in['identity'] == {'role': 'farmer', 'actor_id': 'farmer-nalgonda-1'}
    assert client.get('/api/v1/officer/queue').status_code == 403
    monkeypatch.setattr(api, 'settings', replace(api.settings, demo_mode=False))
    assert client.post('/api/v1/session', json={'username': 'rajesh', 'password': '123'}).status_code == 503


@pytest.mark.parametrize('decision', ['accepted', 'rejected'])
def test_ai_review_persists_decision_and_farmer_response_with_version_guards(client, monkeypatch, decision):
    import backend.api as api
    async def answer(*args):
        return {'summary': 'Observe affected and healthy leaves.', 'uncertainty': 'A local inspection is needed.',
                'actions': [], 'possible_causes': [], 'summary_source_ids': [], 'answer_basis': 'general',
                'needs_officer_review': False, 'provider': 'Google Gemini API', 'model': 'mock-flash', 'live_model_call': True}
    monkeypatch.setattr(api, 'generate_advisory', answer)
    case = client.post('/api/v1/cases', data={'field_id': 'field-nalgonda-rice-1', 'question': 'What should I observe?', 'language': 'en'}).json()
    case_id = case['id']
    assert client.post(f'/api/v1/cases/{case_id}/contact-officer', data={
        'expected_version': 1, 'name': 'Synthetic Farmer', 'phone': '9876543210',
        'location': 'Nalgonda, Telangana', 'query': 'Please check the answer.', 'consent': 'true'}).status_code == 200
    client.post('/api/v1/session', json={'username': 'priya', 'password': '123'})
    payload = {'expected_version': 2, 'status': 'approved', 'ai_decision': decision,
               'note': 'Arrange a local field inspection.' if decision == 'rejected' else ''}
    endpoint = f'/api/v1/officer/cases/{case_id}/review'
    assert client.post(endpoint, json=payload).status_code == 403
    client.post('/api/v1/session', json={'username': 'rajesh', 'password': '123'})
    if decision == 'rejected':
        for note in ('', '   ', 'short'):
            assert client.post(endpoint, json={**payload, 'note': note}).status_code == 422
    reviewed = client.post(endpoint, json=payload)
    assert reviewed.status_code == 200
    assert reviewed.json()['status'] == 'approved'
    assert reviewed.json()['reviews'][-1]['ai_decision'] == decision
    assert client.post(endpoint, json=payload).status_code == 409
    assert client.get('/api/v1/officer/advisories').json() == []
    assert client.get(f'/api/v1/officer/cases/{case_id}/reviews').json()[0]['ai_decision'] == decision
    client.post('/api/v1/session', json={'username': 'ramesh', 'password': '123'})
    farmer_case = client.get('/api/v1/cases/my').json()[0]
    assert farmer_case['reviews'][-1]['note'] == payload['note']
    assert farmer_case['reviews'][-1]['ai_decision'] == decision
    assert farmer_case['advisory'] == case['advisory']
    assert farmer_case['evidence'] == case['evidence']
    client.post('/api/v1/session', json={'username': 'rajesh', 'password': '123'})
    assert client.post(endpoint, json={'expected_version': 3, 'status': 'resolved'}).status_code == 200
    assert client.post(endpoint, json={**payload, 'expected_version': 4}).status_code == 409


def test_unavailable_ai_cannot_be_accepted_but_officer_can_answer(client):
    case = client.post('/api/v1/cases', data={'field_id': 'field-nalgonda-rice-1', 'question': 'What should I check?', 'language': 'en'}).json()
    assert case['provider'] != 'Google Gemini API'
    client.post('/api/v1/session', json={'username': 'rajesh', 'password': '123'})
    endpoint = f"/api/v1/officer/cases/{case['id']}/review"
    assert client.post(endpoint, json={'expected_version': 1, 'status': 'approved', 'ai_decision': 'accepted'}).status_code == 422
    response = client.post(endpoint, json={'expected_version': 1, 'status': 'approved', 'note': 'Arrange a local field inspection.'})
    assert response.status_code == 200
    assert response.json()['reviews'][-1]['ai_decision'] is None


def test_maize_publication_reaches_only_matching_andhra_field_and_expires(client):
    import backend.api as api
    from backend.database import connect
    import json
    client.post('/api/v1/session', json={'username': 'anil', 'password': '123'})
    case = client.post('/api/v1/cases', data={'field_id': 'field-khammam-maize-1', 'question': 'What should I observe in maize?', 'language': 'en'}).json()
    client.post('/api/v1/session', json={'username': 'rajesh', 'password': '123'})
    client.post(f"/api/v1/officer/cases/{case['id']}/review", json={'expected_version': 1, 'status': 'approved', 'note': 'Observe before changing treatment.'})
    published = client.post('/api/v1/officer/advisories', json={'title': 'Maize field observations', 'body': 'Observe changing leaves and ask an officer to inspect before changing treatment.', 'source_case_id': case['id']})
    assert published.status_code == 200
    rows = client.get('/api/v1/officer/exchanges').json()
    assert len(rows) == 1 and rows[0]['payload']['crop'] == 'Maize'
    client.post('/api/v1/session', json={'username': 'lakshmi', 'password': '123'})
    fields = {field['crop']: field['id'] for field in client.get('/api/v1/fields').json()}
    assert client.get(f"/api/v1/fields/{fields['Rice']}/feed").json() == []
    assert client.get(f"/api/v1/fields/{fields['Maize']}/feed").json()[0]['title'] == 'Maize field observations'
    with connect() as db:
        payload = rows[0]['payload']
        payload['valid_until'] = '2000-01-01T00:00:00+00:00'
        db.execute('UPDATE exchange_receipts SET payload_json=? WHERE id=?', (json.dumps(payload), rows[0]['id']))
    assert client.get(f"/api/v1/fields/{fields['Maize']}/feed").json() == []


def test_pitch_cleanup_backs_up_linked_history_and_keeps_unique_cases(client):
    import backend.api as api
    from backend.database import connect
    from scripts.prepare_pitch_data import prepare
    import sqlite3
    question = 'How should I observe the rice leaves?'
    first = client.post('/api/v1/cases', data={'field_id': 'field-nalgonda-rice-1', 'question': question, 'language': 'en'}).json()
    duplicate = client.post('/api/v1/cases', data={'field_id': 'field-nalgonda-rice-1', 'question': question.upper(), 'language': 'en'}).json()
    rehearsal = client.post('/api/v1/cases', data={'field_id': 'field-nalgonda-rice-1', 'question': 'Several lower rice leaves changed color. Ref testabc.', 'language': 'en'}).json()
    client.post('/api/v1/session', json={'username': 'rajesh', 'password': '123'})
    for case in (first, rehearsal):
        client.post(f"/api/v1/officer/cases/{case['id']}/review", json={'expected_version': 1, 'status': 'approved'})
        assert client.post('/api/v1/officer/advisories', json={'title': 'Rice field observations', 'body': 'Observe leaves before changing treatment and ask a local officer for confirmation.', 'source_case_id': case['id']}).status_code == 200
    planned = prepare(api.settings.database_path)
    assert set(planned['removed_case_ids']) == {duplicate['id'], rehearsal['id']}
    assert planned['backup'] is None
    with connect() as db:
        assert db.execute('SELECT COUNT(*) FROM cases').fetchone()[0] == 3
    applied = prepare(api.settings.database_path, apply=True)
    with sqlite3.connect(applied['backup']) as backup:
        assert backup.execute('SELECT COUNT(*) FROM cases').fetchone()[0] == 3
        assert backup.execute('SELECT COUNT(*) FROM exchange_receipts').fetchone()[0] == 2
    with connect() as db:
        assert db.execute('SELECT id FROM cases').fetchone()[0] == first['id']
        assert db.execute('SELECT COUNT(*) FROM advisories').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM exchange_receipts').fetchone()[0] == 1
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert prepare(api.settings.database_path, apply=True)['removed_case_ids'] == []
