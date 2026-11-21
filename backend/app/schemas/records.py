from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.outputs import MeaningCheck, ProviderName


class RecordSentence(BaseModel):
    sentence_id: str = Field(pattern=r"^R\d{3,}$")
    text: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    heading: str | None = None


class RecordExplainRequest(BaseModel):
    text: str
    language: Literal["en", "sv"] = "en"
    provider: ProviderName | None = None

    @field_validator("text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Record text must not be empty")
        return v


class PlainStatement(BaseModel):
    statement_id: str
    source_sentence_ids: list[str] = Field(min_length=1)
    text: str = Field(min_length=1)
    meaning_checks: list[MeaningCheck] = Field(default_factory=list)
    risk: Literal["low", "medium", "high"] = "low"
    terms_explained: list[str] = Field(default_factory=list)


class RecordExplainResponse(BaseModel):
    created_at: datetime
    language: str
    provider: ProviderName
    provider_label: str
    model: str | None = None
    sentences: list[RecordSentence]
    statements: list[PlainStatement]
    unexplained_sentence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    plain_text: str = ""
    disclaimer: str = ("Plain-language version for information only. It may simplify or miss nuances; flagged "
                       "sentences should be compared with the original. Not medical advice.")
