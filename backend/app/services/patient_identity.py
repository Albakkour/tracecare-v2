"""Patient identity for the demo: display name and a *temporary* Swedish-style personnummer.

Real personnummer are 10/12 digits (YYYYMMDD-NNNC). TraceCare only accepts a temporary number in the
reserve-number style ``YYYYMMDD-TNNN`` — the letter ``T`` makes it impossible to be a real personal
identity number, so the prototype cannot be used to store a real person's identifier. Anything that
looks like a real personnummer is rejected, both in the patient field and inside the transcript.
"""

from __future__ import annotations

import random
import re
from datetime import date

from app.schemas.facts import EvidenceReference
from app.schemas.transcript import TranscriptSegment
from app.services.evidence_validator import locate_quote

TEMP_PNR_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})-T(\d{3})$")
# 6 or 8 digit date part, optional -/+ separator, 4 digits: the shape of a real personnummer.
REAL_PNR_RE = re.compile(r"(?<![\dA-Za-z])(?:19|20)?\d{6}[-+]?\d{4}(?![\dA-Za-z])")

GREETING_RE = re.compile(
    r"\b(?:hello|hi|hey|good (?:morning|afternoon|evening)|welcome|nice to (?:meet|see) you|you're welcome)"
    r"[\s,]+(?:(?:mr|mrs|ms|miss)\.?\s+)?(?P<name>[A-Za-z][a-z'\-]{1,30})\b",
    re.IGNORECASE,
)
NOT_NAMES = {"doctor", "there", "everyone", "again", "today", "dr", "sir", "madam", "nurse", "how", "thanks",
             "thank", "so", "okay", "ok", "and", "i", "it", "nice", "good", "to", "you", "back", "all", "guys"}


def validate_temp_personnummer(value: str) -> tuple[str, date]:
    """Return (normalized value, birth date). Raises ValueError with a user-safe message."""
    v = value.strip().upper().replace(" ", "")
    if REAL_PNR_RE.fullmatch(v):
        raise ValueError("Real personnummer are not accepted in this prototype. Use a temporary number "
                         "in the format YYYYMMDD-TNNN (synthetic data only).")
    m = TEMP_PNR_RE.match(v)
    if not m:
        raise ValueError("Temporary personnummer must use the format YYYYMMDD-TNNN, e.g. 19850412-T123.")
    try:
        birth = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError as exc:
        raise ValueError("Temporary personnummer contains an invalid date.") from exc
    if not (1900 <= birth.year <= date.today().year) or birth > date.today():
        raise ValueError("Temporary personnummer contains an implausible birth date.")
    return v, birth


def generate_temp_personnummer(rng: random.Random | None = None) -> str:
    rng = rng or random.SystemRandom()
    today = date.today()
    while True:
        year = rng.randint(today.year - 90, today.year - 18)
        try:
            birth = date(year, rng.randint(1, 12), rng.randint(1, 28))
        except ValueError:
            continue
        return f"{birth:%Y%m%d}-T{rng.randint(0, 999):03d}"


def age_on(birth: date, today: date | None = None) -> int:
    today = today or date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def contains_real_personnummer(text: str) -> bool:
    return bool(REAL_PNR_RE.search(text))


def detect_patient_name(segments: list[TranscriptSegment]) -> tuple[str, EvidenceReference] | None:
    """Find the patient's first name in a clinician greeting, e.g. "Hello, Lisa." (source-linked)."""
    clinician = [s for s in segments if s.speaker == "clinician"]
    # Greetings usually open or close the consultation.
    for seg in clinician[:3] + clinician[-3:]:
        for m in GREETING_RE.finditer(seg.text):
            name = m.group("name")
            if name.lower() in NOT_NAMES:
                continue
            ref = locate_quote(name, seg)
            if ref.quote_match != "not_found":
                return name[:1].upper() + name[1:].lower(), ref
    return None
