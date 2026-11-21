from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.facts import EvidenceReference

ItemStatus = Literal[
    "asked_and_addressed",
    "asked_but_unanswered",
    "volunteered_not_asked",
    "not_found_in_transcript",
    "unclear_needs_review",
    "not_applicable",
]
ReviewState = Literal["provisional", "needs_review", "reviewed"]

ITEM_STATUSES: tuple[str, ...] = ItemStatus.__args__  # type: ignore[attr-defined]


class ChecklistItem(BaseModel):
    item_id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1)
    dimension: str | None = Field(default=None, description="Shared documentation dimension, e.g. onset")
    description: str | None = None
    example_questions: list[str] = Field(default_factory=list)
    reviewer_confirmation_recommended: bool = True


class ChecklistTemplate(BaseModel):
    template_id: str = Field(pattern=r"^[a-z0-9_]+$")
    version: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = ""
    category: str = Field(min_length=1)
    trigger_concepts: list[str] = Field(default_factory=list)
    status: Literal["demo_not_clinically_validated"]
    review_required: bool = True
    source: str = ""
    clinical_reviewer: str | None = None
    approval_status: str = "not_approved"
    disclaimer: str = ""
    items: list[ChecklistItem] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_item_ids(self) -> "ChecklistTemplate":
        ids = [i.item_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate checklist item IDs in template {self.template_id}")
        return self

    def item_ids(self) -> set[str]:
        return {i.item_id for i in self.items}


class ChecklistAssessment(BaseModel):
    item_id: str
    label: str
    status: ItemStatus
    clinician_question_segment_ids: list[str] = Field(default_factory=list)
    clinician_question_quotes: list[str] = Field(default_factory=list)
    information_segment_ids: list[str] = Field(default_factory=list)
    information_quotes: list[str] = Field(default_factory=list)
    question_evidence: list[EvidenceReference] = Field(default_factory=list)
    information_evidence: list[EvidenceReference] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    proposed_status: ItemStatus | None = Field(default=None, description="Status suggested by the provider")
    rationale: str | None = None
    review_state: ReviewState = "provisional"
    reviewed: bool = False
    not_applicable_reason: str | None = None
    reviewer_note: str | None = None
    validation_notes: list[str] = Field(default_factory=list)


class CoverageMetric(BaseModel):
    label: str
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    percentage: float | None
    available: bool
    message: str | None = None


class CoverageReport(BaseModel):
    coverage_available: bool
    message: str | None = None
    template_id: str | None = None
    template_version: str | None = None
    template_name: str | None = None
    template_status: str | None = None
    question_coverage: CoverageMetric | None = None
    information_capture: CoverageMetric | None = None
    assessable_count: int = 0
    pending_review_count: int = 0
    not_applicable_count: int = 0
    not_found_count: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    is_provisional: bool = True
    review_status: Literal["provisional", "reviewed"] = "provisional"
    items: list[ChecklistAssessment] = Field(default_factory=list)
    disclaimer: str = (
        "Coverage describes only what this transcript shows against a demo checklist. "
        "It is not a clinician performance score, clinical quality score, or standard of care."
    )
