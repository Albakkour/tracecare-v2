"""Deterministic transcript segmentation.

Accepted line formats (one speaker turn per line):
    Doctor: What brings you here today?
    [doctor] what brings you here today
    Patient - I've had a headache.

Speakers are never inferred. A line without a recognisable speaker label becomes its own segment
with speaker ``unknown`` and a parse warning, so a reviewer can correct the transcript.
"""

from __future__ import annotations

import re

from app.schemas.transcript import ParsedTranscript, Speaker, TranscriptSegment

CLINICIAN_LABELS = {
    "doctor", "dr", "clinician", "physician", "provider", "nurse", "gp", "md", "np", "pa", "practitioner",
}
PATIENT_LABELS = {"patient", "pt"}
OTHER_LABELS = {
    "patient_guest", "guest", "partner", "parent", "mother", "father", "mom", "dad", "caregiver", "carer",
    "family", "family member", "relative", "spouse", "husband", "wife", "son", "daughter", "interpreter",
    "friend", "companion",
}

# [label] text
_BRACKET_RE = re.compile(r"^\s*\[(?P<label>[A-Za-z][A-Za-z _\-]{0,30})\]\s*(?:[:\-–]\s*)?(?P<text>.*)$")
# Label: text   or   Label - text
_COLON_RE = re.compile(r"^\s*(?P<label>[A-Za-z][A-Za-z .\-_]{0,30}?)\s*(?::|\s-\s)\s*(?P<text>.*)$")


def classify_label(raw_label: str) -> Speaker | None:
    label = raw_label.strip().lower().rstrip(".")
    label = re.sub(r"\s+", " ", label)
    if label in CLINICIAN_LABELS or label.startswith(("doctor ", "dr ", "dr. ", "nurse ")):
        return "clinician"
    if label in PATIENT_LABELS or label.startswith("patient "):
        return "patient"
    if label in OTHER_LABELS:
        return "other"
    return None


def normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def parse_transcript(transcript: str) -> ParsedTranscript:
    normalized = normalize_line_endings(transcript)
    segments: list[TranscriptSegment] = []
    warnings: list[str] = []
    unlabelled_lines = 0

    offset = 0
    for line in normalized.split("\n"):
        line_start = offset
        offset += len(line) + 1  # +1 for the newline removed by split
        if not line.strip():
            continue

        speaker: Speaker = "unknown"
        speaker_label: str | None = None
        text_start_in_line: int

        match = _BRACKET_RE.match(line) or _COLON_RE.match(line)
        classified = classify_label(match.group("label")) if match else None
        if match and classified:
            speaker = classified
            speaker_label = match.group("label").strip()
            text_start_in_line = match.start("text")
        else:
            unlabelled_lines += 1
            text_start_in_line = len(line) - len(line.lstrip())

        raw_text = line[text_start_in_line:]
        text = raw_text.strip()
        if not text:
            # A label with no utterance carries no content to cite.
            continue
        start = line_start + text_start_in_line + (len(raw_text) - len(raw_text.lstrip()))
        end = start + len(text)
        assert normalized[start:end] == text  # offsets are computed, never guessed

        segments.append(
            TranscriptSegment(
                segment_id=f"S{len(segments) + 1:03d}",
                speaker=speaker,
                speaker_label=speaker_label,
                text=text,
                start_char=start,
                end_char=end,
                turn_index=len(segments) + 1,
            )
        )

    if not segments:
        warnings.append("No transcript segments were found.")
    if unlabelled_lines:
        warnings.append(
            f"{unlabelled_lines} line(s) had no recognised speaker label (expected e.g. 'Doctor:' / 'Patient:' "
            "or '[doctor]' / '[patient]'). Their speaker is shown as 'unknown' and was not inferred; "
            "please correct the transcript."
        )
    speakers = {s.speaker for s in segments}
    if segments and "clinician" not in speakers:
        warnings.append("No clinician turns were identified; clinician question coverage cannot be assessed reliably.")
    if segments and "patient" not in speakers:
        warnings.append("No patient turns were identified.")

    return ParsedTranscript(normalized_text=normalized, segments=segments, warnings=warnings)
