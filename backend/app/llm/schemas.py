"""Schemas for *candidate* output proposed by an LLM provider.

These are deliberately simple (no regex constraints) so they work with structured outputs. Every
value here is untrusted until the evidence validator has checked it against the transcript.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.coverage import ItemStatus
from app.schemas.facts import Certainty, FactCategory, Polarity, Temporality


class FactCandidate(BaseModel):
    fact_id: str = Field(description="Unique ID such as F001, F002, ...")
    category: FactCategory
    concept: str = Field(description="Short normalized concept label, e.g. 'headache', 'fever'")
    normalized_value: str = Field(description="Concise meaning without adding information")
    polarity: Polarity
    certainty: Certainty
    temporality: Temporality
    duration: str | None = None
    frequency: str | None = None
    severity: str | None = None
    location: str | None = None
    context: str | None = None
    source_segment_ids: list[str] = Field(description="Segment IDs (e.g. S002) that support this fact")
    supporting_quote: str = Field(description="Verbatim text copied exactly from one of the source segments")


class SymptomCandidate(BaseModel):
    concept: str
    polarity: Polarity
    fact_ids: list[str]
    source_segment_ids: list[str]
    supporting_quote: str
    template_id: str | None = Field(description="An allowed template ID, or null if none fits")


class ChecklistCandidate(BaseModel):
    template_id: str
    item_id: str
    proposed_status: ItemStatus
    clinician_question_segment_ids: list[str]
    clinician_question_quotes: list[str]
    information_segment_ids: list[str]
    information_quotes: list[str]
    fact_ids: list[str]
    confidence: Literal["high", "low"]
    rationale: str


class ExtractionOutput(BaseModel):
    facts: list[FactCandidate]
    symptoms: list[SymptomCandidate]
    checklist_assessments: list[ChecklistCandidate]


class PatientStatementCandidate(BaseModel):
    text: str
    fact_ids: list[str]


class PatientExplanationOutput(BaseModel):
    statements: list[PatientStatementCandidate]
