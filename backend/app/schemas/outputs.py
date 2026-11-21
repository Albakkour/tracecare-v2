from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.coverage import CoverageReport, ItemStatus
from app.schemas.facts import EvidenceReference, MedicalFact, SymptomMention
from app.schemas.transcript import TranscriptSegment

ProviderName = Literal["demo", "anthropic"]

CLINICAL_NOTE_DISCLAIMER = (
    "Draft — clinician review required. Generated from the transcript only; contains no diagnosis, "
    "examination findings, or treatment plan."
)
PATIENT_EXPLANATION_DISCLAIMER = (
    "This explanation is for information only. It describes what was said in the conversation. "
    "It is not a diagnosis and not a substitute for medical advice."
)


class ValidationFinding(BaseModel):
    code: str
    severity: Literal["error", "warning", "info"]
    message: str
    ref_type: Literal["fact", "symptom", "checklist_item", "statement", "template", "transcript"] | None = None
    ref_id: str | None = None


class MeaningCheck(BaseModel):
    """Deterministic checks that a rewritten sentence kept the meaning of its source facts."""

    check: Literal["negation", "uncertainty", "number"]
    message: str


class GeneratedStatement(BaseModel):
    statement_id: str
    section: str
    text: str = Field(min_length=1)
    fact_ids: list[str] = Field(default_factory=list)
    checklist_item_id: str | None = None
    kind: Literal["fact", "coverage_gap"] = "fact"
    needs_review: bool = False
    review_notes: list[str] = Field(default_factory=list)
    meaning_checks: list[MeaningCheck] = Field(default_factory=list)


class NoteSection(BaseModel):
    section_id: str
    heading: str
    statements: list[GeneratedStatement] = Field(default_factory=list)
    empty_message: str = "Not established in this transcript."


class ClinicalNote(BaseModel):
    title: str = "Draft clinical note"
    status: Literal["draft_clinician_review_required"] = "draft_clinician_review_required"
    disclaimer: str = CLINICAL_NOTE_DISCLAIMER
    sections: list[NoteSection] = Field(default_factory=list)


class PatientExplanation(BaseModel):
    language: str = "en"
    disclaimer: str = PATIENT_EXPLANATION_DISCLAIMER
    intro: str = "Here is a plain-language summary of what was discussed in your consultation."
    statements: list[GeneratedStatement] = Field(default_factory=list)
    not_established: list[str] = Field(
        default_factory=list, description="Topics that were not established in the conversation"
    )
    section_headings: dict[str, str] = Field(default_factory=dict)
    plain_text: str = Field(default="", description="The complete summary as plain text, ready to copy")


class PatientInfo(BaseModel):
    """Patient details entered by the user. Synthetic / role-play only."""

    display_name: str | None = Field(default=None, max_length=80)
    temp_personnummer: str | None = Field(default=None, description="Temporary number YYYYMMDD-TNNN")

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        if any(ch.isdigit() for ch in v):
            raise ValueError("Name must not contain digits")
        return v or None

    @field_validator("temp_personnummer")
    @classmethod
    def check_pnr(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        from app.services.patient_identity import validate_temp_personnummer

        return validate_temp_personnummer(v)[0]


class PatientSummary(BaseModel):
    display_name: str | None = None
    name_source: Literal["entered", "detected"] | None = None
    name_evidence: EvidenceReference | None = None
    temp_personnummer: str | None = None
    birth_date: date | None = None
    age: int | None = None
    is_synthetic: bool = True


class AnalyzeRequest(BaseModel):
    transcript: str
    language: Literal["en", "sv"] = Field(default="en", description="Language of the patient summary")
    template_ids: list[str] = Field(default_factory=list)
    provider: ProviderName | None = None
    patient: PatientInfo | None = None

    @field_validator("transcript")
    @classmethod
    def transcript_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Transcript must not be empty")
        return v


class AnalyzeResponse(BaseModel):
    encounter_id: str
    created_at: datetime
    status: Literal["provisional_review_required", "reviewed"] = "provisional_review_required"
    provider: ProviderName
    provider_label: str
    model: str | None = None
    language: str = "en"
    patient: PatientSummary = Field(default_factory=PatientSummary)
    chief_concern: str | None = None
    segments: list[TranscriptSegment]
    facts: list[MedicalFact] = Field(description="Facts usable in outputs (source-linked or needs review)")
    rejected_facts: list[MedicalFact] = Field(default_factory=list, description="Facts excluded by validation")
    symptoms: list[SymptomMention] = Field(default_factory=list)
    coverage_reports: list[CoverageReport] = Field(default_factory=list)
    clinical_note: ClinicalNote
    patient_explanation: PatientExplanation
    validation_findings: list[ValidationFinding] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    persisted: bool = False


class CoverageItemUpdate(BaseModel):
    """Reviewer override for one checklist item. The backend recalculates the metrics."""

    status: ItemStatus | None = None
    not_applicable_reason: str | None = None
    confirm: bool = Field(default=False, description="Mark the (possibly changed) status as reviewed")
    reviewer_note: str | None = Field(default=None, max_length=500)
