from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DemoSessionRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class Cause(BaseModel):
    label: str = Field(max_length=120)
    visual_reason: str = Field(max_length=200)
    source_ids: list[str] = Field(default_factory=list, max_length=4)


class AdvisoryAction(BaseModel):
    text: str = Field(max_length=180)
    source_ids: list[str] = Field(default_factory=list, max_length=4)


class GeminiAdvisory(BaseModel):
    summary: str = Field(max_length=300)
    summary_source_ids: list[str] = Field(default_factory=list, max_length=4)
    possible_causes: list[Cause] = Field(default_factory=list, max_length=2)
    uncertainty: str = Field(max_length=180)
    needs_officer_review: bool = False
    review_reason: str = Field(default="", max_length=200)
    answer_basis: Literal["research", "mixed", "general"]
    actions: list[AdvisoryAction] = Field(default_factory=list, max_length=2)
    clarifying_question: str | None = Field(default=None, min_length=4, max_length=200)


class ReviewRequest(BaseModel):
    status: Literal["needs_information", "approved", "rejected", "resolved"]
    note: str = Field(default="", max_length=1200)
    expected_version: int = Field(ge=1)
    ai_decision: Literal["accepted", "rejected"] | None = None


class FarmerReplyRequest(BaseModel):
    text: str = Field(min_length=4, max_length=1500)
    expected_version: int = Field(ge=1)


class PublishAdvisoryRequest(BaseModel):
    title: str = Field(min_length=4, max_length=120)
    body: str = Field(min_length=10, max_length=1800)
    valid_days: int = Field(default=14, ge=1, le=60)
    source_case_id: str


class RegionalAdvisoryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    contract_version: Literal["1.0"] = "1.0"
    event_id: str
    advisory_version: int = Field(ge=1)
    source_state: Literal["Telangana"]
    target_state: Literal["Andhra Pradesh"]
    source_district: str = Field(min_length=2, max_length=80)
    target_district: str = Field(min_length=2, max_length=80)
    crop: Literal["Rice", "Maize"]
    title: str = Field(min_length=4, max_length=120)
    body: str = Field(min_length=10, max_length=1800)
    issued_at: str
    valid_until: str
    review_attribution: str = Field(min_length=1, max_length=80)
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)


class CaseResponse(BaseModel):
    id: str
    field_id: str
    state: str
    district: str
    crop: str
    question: str
    transcript: str | None = None
    status: str
    provider: str
    model: str | None = None
    advisory: dict
    evidence: list[dict]
    photo_shared_with_officer: bool
    created_at: str
    version: int
