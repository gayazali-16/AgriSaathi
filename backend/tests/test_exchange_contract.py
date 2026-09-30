import pytest
from pydantic import ValidationError

from backend.exchange import STATE_ADAPTERS, build_regional_contract
from backend.schemas import RegionalAdvisoryV1


def test_regional_contract_is_versioned_minimal_and_excludes_photo_ids():
    advisory = {
        "id": "regional-demo-1", "version": 2,
        "state": "Telangana", "district": "Nalgonda", "crop": "Rice",
        "title": "Rice leaf observations", "body": "Ask a local extension officer to confirm the observation.",
        "issued_at": "2026-09-23T10:00:00+00:00", "valid_until": "2026-10-07T10:00:00+00:00",
    }
    evidence_ids = ["user-photo", *(f"source-{index}" for index in range(10))]
    contract = build_regional_contract(advisory, STATE_ADAPTERS["Andhra Pradesh"], evidence_ids)
    payload = contract.model_dump()

    assert payload["contract_version"] == "1.0"
    assert payload["target_state"] == "Andhra Pradesh"
    assert payload["target_district"] == "Krishna"
    assert payload["event_id"] == "advisory:regional-demo-1:v2"
    assert payload["evidence_ids"] == [f"source-{index}" for index in range(8)]
    assert "user-photo" not in str(payload)
    assert "farmer_id" not in payload and "question" not in payload


def test_regional_contract_rejects_unrecognized_fields_and_wrong_receiver():
    advisory = {
        "id": "regional-demo-2", "version": 1,
        "state": "Telangana", "district": "Nalgonda", "crop": "Maize",
        "title": "Maize crop observations", "body": "Check crop symptoms with an extension officer before acting.",
        "issued_at": "2026-09-23T10:00:00+00:00", "valid_until": "2026-10-07T10:00:00+00:00",
    }
    valid = build_regional_contract(advisory, STATE_ADAPTERS["Andhra Pradesh"], [])
    with pytest.raises(ValidationError):
        RegionalAdvisoryV1(**{**valid.model_dump(), "farmer_phone": "9876543210"})
    with pytest.raises(ValidationError):
        RegionalAdvisoryV1(**{**valid.model_dump(), "target_state": "Karnataka"})
