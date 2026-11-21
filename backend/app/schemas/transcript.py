from typing import Literal

from pydantic import BaseModel, Field

Speaker = Literal["clinician", "patient", "other", "unknown"]


class TranscriptSegment(BaseModel):
    segment_id: str = Field(pattern=r"^S\d{3,}$")
    speaker: Speaker
    speaker_label: str | None = Field(default=None, description="Label exactly as written in the transcript")
    text: str = Field(min_length=1, description="Exact original utterance text (label removed)")
    start_char: int = Field(ge=0, description="Offset of `text` in the line-ending-normalized transcript")
    end_char: int = Field(ge=0)
    turn_index: int = Field(ge=1)


class ParsedTranscript(BaseModel):
    normalized_text: str
    segments: list[TranscriptSegment]
    warnings: list[str] = Field(default_factory=list)
