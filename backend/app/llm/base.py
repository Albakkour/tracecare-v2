from __future__ import annotations

from typing import Protocol

from app.llm.schemas import ExtractionOutput, PatientExplanationOutput
from app.schemas.coverage import ChecklistTemplate
from app.schemas.facts import MedicalFact
from app.schemas.transcript import TranscriptSegment


class ProviderError(Exception):
    """A provider failure with a message that is safe to show to the user."""

    def __init__(self, kind: str, user_message: str, status_code: int = 502):
        super().__init__(user_message)
        self.kind = kind
        self.user_message = user_message
        self.status_code = status_code


class LLMProvider(Protocol):
    name: str
    label: str
    model: str | None

    def extract(self, segments: list[TranscriptSegment], templates: list[ChecklistTemplate]) -> ExtractionOutput:
        """Propose candidate facts, symptom mentions, and checklist evidence."""
        ...

    def explain_for_patient(self, facts: list[MedicalFact], language: str) -> PatientExplanationOutput:
        """Rewrite accepted facts into plain language, keeping fact IDs."""
        ...

    def simplify_record(self, sentences, language: str):
        """Rewrite record sentences into plain language, citing sentence IDs."""
        ...
