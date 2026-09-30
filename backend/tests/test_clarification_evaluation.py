import json

import pytest
from pydantic import ValidationError

from backend.ai_service import _contents, _contains_unsupported_rate
from backend.schemas import GeminiAdvisory
from scripts.evaluate_advisories import SCENARIOS, score


def test_clarifying_question_is_bounded_optional_and_language_prompted():
    base = dict(summary='Observe the leaves.', uncertainty='No inspection.', answer_basis='general')
    assert GeminiAdvisory(**base).clarifying_question is None
    answer = GeminiAdvisory(**base, clarifying_question='When did the symptoms start?')
    assert answer.clarifying_question
    with pytest.raises(ValidationError):
        GeminiAdvisory(**base, clarifying_question='x' * 201)
    prompt = _contents('Yellow leaves', 'Rice', 'hi', [], None, None)[0]
    assert 'clarifying_question' in prompt and "farmer's language" in prompt
    assert _contains_unsupported_rate(GeminiAdvisory(**base, clarifying_question='Did you apply 2 kg/acre of fertilizer?'))


def test_self_authored_evaluation_has_no_accuracy_claim_or_mock_live_score():
    scenarios = json.loads(SCENARIOS.read_text(encoding='utf-8'))
    assert len(scenarios) == 25
    assert len({s['id'] for s in scenarios}) == 25
    assert {s['crop'] for s in scenarios} == {'Rice', 'Maize'}
    assert {s['language'] for s in scenarios} == {'en', 'hi', 'te'}
    assert sum(s.get('unsupported', False) for s in scenarios) >= 10
    assert score(scenarios[0], {'live_model_call': False}) == 'honest_abstention'
    assert score(scenarios[0], {'live_model_call': True}) == 'clarification_missing'
