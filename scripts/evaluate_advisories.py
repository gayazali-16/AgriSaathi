"""Self-authored text scenarios; structural checks, never a field accuracy benchmark."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

from backend import ai_service as ai
from backend.config import ROOT
from backend.data_service import climate_evidence, evidence_for_field, practice_evidence, satellite_evidence, soil_evidence
from backend.database import DEMO_FIELDS, utc_now

SCENARIOS = ROOT / 'backend/data/evaluation/scenarios.json'


def score(scenario: dict, answer: dict) -> str:
    if not answer.get('live_model_call'):
        return 'honest_abstention'
    if scenario.get('expect_clarification') and not answer.get('clarifying_question'):
        return 'clarification_missing'
    return 'validated_response'


async def evaluate(live: bool, retry_from: Path | None = None) -> dict:
    scenarios = json.loads(SCENARIOS.read_text(encoding='utf-8'))
    if retry_from:
        previous = json.loads(retry_from.read_text(encoding='utf-8'))
        retry_ids = {row['id'] for row in previous['results'] if row['status'] == 'provider_unavailable'}
        scenarios = [scenario for scenario in scenarios if scenario['id'] in retry_ids]
    if live and not ai.get_settings().gemini_api_key:
        raise SystemExit('A server-side Gemini key is required for --live. No live results were recorded.')
    if not live:
        ai.settings = replace(ai.get_settings(), gemini_api_key='')
    results = []
    evidence_hashes = {}
    for scenario in scenarios:
        field = next(row for row in DEMO_FIELDS if row['crop'] == scenario['crop'])
        evidence = evidence_for_field(field) + practice_evidence(field, scenario['language'])
        evidence += [item for item in [climate_evidence(field), soil_evidence(field), satellite_evidence(field)] if item]
        evidence_hashes[scenario['id']] = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
        started = time.monotonic()
        try:
            answer = await ai.generate_advisory(scenario['question'], scenario['crop'], scenario['language'], evidence, None, None)
            status = score(scenario, answer)
        except (ValueError, RuntimeError) as exc:
            answer = {'live_model_call': False, 'failure_category': ai.failure_category(exc)}
            status = 'rejected_output' if answer['failure_category'] == 'schema' else 'provider_unavailable'
        result = {'id': scenario['id'], 'status': status, 'duration_seconds': round(time.monotonic() - started, 2), 'answer': answer}
        results.append(result)
        print(f"{scenario['id']}: {status} ({result['duration_seconds']}s)", flush=True)
    return {'run_at': utc_now(), 'mode': 'live' if live else 'offline', 'prompt_version': ai.PROMPT_VERSION,
            'retry_from': str(retry_from) if retry_from else None,
            'configured_models': [ai.get_settings().gemini_model, *ai.GEMINI_FALLBACK_MODELS],
            'sdk_version': importlib.metadata.version('google-genai'),
            'scenario_sha256': hashlib.sha256(SCENARIOS.read_bytes()).hexdigest(),
            'evidence_sha256': evidence_hashes, 'results': results,
            'limits': 'Schema/citation/rate checks and clarification presence only. No expert agronomic or fluent-language accuracy score.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Make 25 sequential real provider calls using the server key.')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/evaluation-results.json')
    parser.add_argument('--retry-from', type=Path, help='Retry only provider-unavailable scenarios; keep the first run intact.')
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.live, args.retry_from))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
