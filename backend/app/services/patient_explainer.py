"""Patient-friendly explanation: validation of rewritten statements + a deterministic demo renderer.

Every statement must cite known, accepted fact IDs. A deterministic "meaning check" flags rewritten
sentences that may have lost a negation, an uncertainty, or a number from their source facts
(inspired by the PLABA plain-language adaptation task: simplified sentences should point back to
their source and flag where meaning might have changed).
"""

from __future__ import annotations

import re

from app.llm.schemas import PatientExplanationOutput, PatientStatementCandidate
from app.schemas.facts import MedicalFact
from app.schemas.outputs import GeneratedStatement, MeaningCheck, ValidationFinding

NEGATION_RE = re.compile(
    r"\b(no|not|never|none|nothing|without|denied|denies|neither|nor)\b|n't\b|n’t\b", re.IGNORECASE)
UNCERTAINTY_RE = re.compile(
    r"\b(not sure|unsure|unclear|uncertain|unknown|not known|not clear|not certain|maybe|might|possibly|"
    r"perhaps|(do|does|did)\s*n['’]?t (remember|know)|(can|could)\s*n['’]?t (remember|recall)|"
    r"not (remember|recall)|forgot|forget|not established|don['’]t know)\b",
    re.IGNORECASE)
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "once": 1, "twice": 2,
    "a week": 1, "a day": 1,
}
_NUM_RE = re.compile(r"\b(\d+(?:\.\d+)?|" + "|".join(k for k in NUMBER_WORDS if " " not in k) + r")\b", re.IGNORECASE)

# Small plain-language glossary used by the demo renderer.
PLAIN_TERMS = {
    "dyspnea": "shortness of breath", "dyspnoea": "shortness of breath", "cephalalgia": "headache",
    "photophobia": "sensitivity to light", "phonophobia": "sensitivity to sound", "emesis": "vomiting",
    "pyrexia": "fever", "febrile": "having a fever", "vertigo": "a spinning feeling (vertigo)",
    "paresthesia": "pins and needles", "tinnitus": "ringing in the ears", "analgesic": "painkiller",
    "nsaid": "anti-inflammatory painkiller", "hypertension": "high blood pressure",
}


def numbers_in(text: str) -> set[float]:
    found: set[float] = set()
    for m in _NUM_RE.finditer(text or ""):
        tok = m.group(1).lower()
        found.add(float(NUMBER_WORDS[tok]) if tok in NUMBER_WORDS else float(tok))
    return found


def meaning_checks(text: str, facts: list[MedicalFact]) -> list[MeaningCheck]:
    checks: list[MeaningCheck] = []
    has_neg = bool(NEGATION_RE.search(text))
    has_unc = bool(UNCERTAINTY_RE.search(text))
    if any(f.polarity == "negative" for f in facts) and not has_neg:
        checks.append(MeaningCheck(check="negation",
                                   message="Source fact is negative, but the sentence has no negation."))
    if facts and all(f.polarity == "positive" for f in facts) and has_neg and not has_unc:
        checks.append(MeaningCheck(check="negation",
                                   message="Sentence contains a negation, but the source facts are positive."))
    if any(f.polarity == "uncertain" for f in facts) and not has_unc:
        checks.append(MeaningCheck(check="uncertainty",
                                   message="Source fact is uncertain, but the sentence does not say so."))
    source_numbers: set[float] = set()
    for f in facts:
        for field in (f.duration, f.frequency, f.severity):
            source_numbers |= numbers_in(field or "")
    missing = source_numbers - numbers_in(text)
    if missing:
        checks.append(MeaningCheck(check="number",
                                   message="A number from the source fact is missing or changed: "
                                           + ", ".join(f"{n:g}" for n in sorted(missing))))
    return checks


def validate_patient_statements(output: PatientExplanationOutput, accepted_facts: list[MedicalFact]
                                ) -> tuple[list[GeneratedStatement], list[ValidationFinding]]:
    by_id = {f.fact_id: f for f in accepted_facts}
    statements: list[GeneratedStatement] = []
    findings: list[ValidationFinding] = []
    for n, cand in enumerate(output.statements, start=1):
        sid = f"P{n:03d}"
        text = (cand.text or "").strip()
        if not text:
            continue
        ids = list(dict.fromkeys(cand.fact_ids))
        unknown = [f for f in ids if f not in by_id]
        if not ids or unknown:
            msg = ("Statement removed: it cites no fact IDs." if not ids else
                   f"Statement removed: it cites unknown or non-accepted fact ID(s) {', '.join(unknown)}.")
            findings.append(ValidationFinding(code="statement_unknown_fact", severity="error", message=msg,
                                              ref_type="statement", ref_id=sid))
            continue
        checks = meaning_checks(text, [by_id[f] for f in ids])
        if checks:
            findings.append(ValidationFinding(code="possible_meaning_change", severity="warning",
                                              ref_type="statement", ref_id=sid,
                                              message="; ".join(c.message for c in checks)))
        statements.append(GeneratedStatement(
            statement_id=sid, section="patient_explanation", text=text, fact_ids=ids,
            needs_review=bool(checks), meaning_checks=checks,
            review_notes=["Possible meaning change — please review."] if checks else []))
    return statements, findings


def _plain(text: str) -> str:
    out = text
    for term, plain in PLAIN_TERMS.items():
        out = re.sub(rf"\b{re.escape(term)}\b", plain, out, flags=re.IGNORECASE)
    return out


def _lower_first(text: str) -> str:
    text = text.strip().rstrip(".")
    return text[:1].lower() + text[1:] if text else text


def template_patient_explanation(facts: list[MedicalFact]) -> PatientExplanationOutput:
    """Deterministic plain-language rendering used by the demo provider (no LLM)."""
    statements: list[PatientStatementCandidate] = []
    for f in facts:
        concept = _plain(f.concept)
        if f.polarity == "negative" and f.category == "medication":
            text = "You said you have not taken medication."
        elif f.polarity == "negative":
            text = f"You said you have not had {concept.lower()}."
        elif f.polarity == "uncertain":
            text = f"It was not clear from the conversation: {_lower_first(_plain(f.normalized_value))}."
        elif f.category == "symptom":
            details = [d for d in (f.duration, f.location, f.frequency, f.severity) if d]
            text = f"You told the clinician about your {concept.lower()}."
            if details:
                text += " Details you mentioned: " + "; ".join(f"\u201c{d}\u201d" for d in details) + "."
        elif f.category == "impact" and f.severity:
            text = f"You described how bad it was as \u201c{f.severity}\u201d."
        elif f.category == "medication":
            text = f"You mentioned taking {concept.lower()}."
        elif f.category in {"history", "allergy", "social"}:
            text = f"You mentioned: {_lower_first(_plain(f.normalized_value))}."
        else:
            text = f"It was noted that {_lower_first(_plain(f.normalized_value))}."
        statements.append(PatientStatementCandidate(text=text, fact_ids=[f.fact_id]))
    return PatientExplanationOutput(statements=statements)
