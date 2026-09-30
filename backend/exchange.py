from __future__ import annotations

from dataclasses import dataclass

from backend.schemas import RegionalAdvisoryV1


@dataclass(frozen=True)
class StateAdapter:
    state: str
    receiving_district: str
    contract_version: str = "1.0"


STATE_ADAPTERS = {
    "Telangana": StateAdapter("Telangana", "Nalgonda"),
    "Andhra Pradesh": StateAdapter("Andhra Pradesh", "Krishna"),
}


def build_regional_contract(advisory: dict, target: StateAdapter, evidence_ids: list[str]) -> RegionalAdvisoryV1:
    source = STATE_ADAPTERS[advisory["state"]]
    return RegionalAdvisoryV1(
        event_id=f"advisory:{advisory['id']}:v{advisory['version']}",
        advisory_version=advisory["version"],
        source_state=source.state,
        target_state=target.state,
        source_district=advisory["district"],
        target_district=target.receiving_district,
        crop=advisory["crop"],
        title=advisory["title"],
        body=advisory["body"],
        issued_at=advisory["issued_at"],
        valid_until=advisory["valid_until"],
        review_attribution=f"{source.state} extension officer",
        evidence_ids=[item for item in evidence_ids if item != "user-photo"][:8],
    )
