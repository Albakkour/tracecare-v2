from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.transcript import Speaker

FactCategory = Literal[
    "symptom", "medication", "allergy", "history", "social", "duration", "frequency", "impact", "other"
]
Polarity = Literal["positive", "negative", "uncertain"]
Certainty = Literal["explicit", "inferred", "unclear"]
Temporality = Literal["current", "historical", "future_or_planned", "unclear"]
EvidenceStatus = Literal["source_linked", "needs_review", "rejected"]
QuoteMatch = Literal["exact", "normalized", "not_found"]


class EvidenceReference(BaseModel):
    """A link from an extracted item to a transcript segment, as validated by the backend."""

    segment_id: str
    speaker: Speaker | None = None
    quote: str
    quote_match: QuoteMatch
    # Absolute offsets of the quote within the normalized transcript, when it was located.
    start_char: int | None = None
    end_char: int | None = None
    segment_exists: bool = True


class MedicalFact(BaseModel):
    fact_id: str = Field(pattern=r"^F\d{3,}$")
    category: FactCategory
    concept: str = Field(min_length=1)
    normalized_value: str = Field(min_length=1)
    polarity: Polarity
    certainty: Certainty
    temporality: Temporality
    duration: str | None = None
    frequency: str | None = None
    severity: str | None = None
    location: str | None = None
    context: str | None = None
    source_segment_ids: list[str] = Field(min_length=1)
    supporting_quote: str = Field(min_length=1)
    # Backend-owned validation results.
    evidence_status: EvidenceStatus = "source_linked"
    evidence: list[EvidenceReference] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class SymptomMention(BaseModel):
    symptom_id: str
    concept: str = Field(min_length=1)
    polarity: Polarity
    fact_ids: list[str] = Field(default_factory=list)
    source_segment_ids: list[str] = Field(default_factory=list)
    supporting_quote: str = Field(min_length=1)
    template_id: str | None = None
    evidence_status: EvidenceStatus = "source_linked"
    evidence: list[EvidenceReference] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)
