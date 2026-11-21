"""Patient after-visit summary: validation of rewritten statements, a deterministic demo renderer, and a
copyable plain-text version.

Every sentence must cite known, accepted fact IDs (what the patient said, and what the clinician said).
Meaning checks flag sentences that may have lost a negation, an uncertainty or a number.
"""

from __future__ import annotations

from app.llm.schemas import PatientExplanationOutput, PatientStatementCandidate
from app.schemas.facts import CLINICIAN_CATEGORIES, MedicalFact
from app.schemas.outputs import GeneratedStatement, ValidationFinding
from app.services.meaning import fact_meaning_checks
from app.services.plain_language import simplify_text

SECTION_ORDER = ["your_concern", "what_you_told", "findings", "assessment", "plan", "follow_up"]
SECTION_HEADINGS = {
    "en": {
        "your_concern": "Why you came", "what_you_told": "What you told the doctor",
        "findings": "What the doctor found", "assessment": "What the doctor thinks",
        "plan": "Treatment, prescriptions and advice", "follow_up": "Follow-up and when to get help",
        "not_established": "Not discussed in this conversation",
    },
    "sv": {
        "your_concern": "Varför du sökte vård", "what_you_told": "Det du berättade för läkaren",
        "findings": "Vad läkaren såg vid undersökningen", "assessment": "Läkarens bedömning",
        "plan": "Behandling, recept och råd", "follow_up": "Uppföljning och när du ska söka vård",
        "not_established": "Togs inte upp i samtalet",
    },
}
DISCLAIMERS = {
    "en": "This summary is for information only. It describes what was said in the conversation. "
          "It is not a diagnosis and not a substitute for medical advice. If anything is unclear, ask your clinic.",
    "sv": "Den här sammanfattningen är endast information. Den beskriver vad som sades under samtalet. "
          "Den är ingen diagnos och ersätter inte medicinsk rådgivning. Kontakta din mottagning om något är oklart.",
}
INTROS = {
    "en": "Here is a plain-language summary of your consultation.",
    "sv": "Här är en sammanfattning av ditt besök på enkel svenska.",
}

# Swedish names for checklist dimensions (used in the "not discussed" list of Swedish summaries).
DIMENSION_LABELS_SV = {
    "onset": "När besvären började", "duration_course": "Hur länge det pågått / förlopp", "location": "Var det sitter",
    "character": "Hur det känns", "severity_impact": "Hur svårt det är / hur det påverkar dig",
    "timing_frequency": "Hur ofta det händer", "modifying_factors": "Vad som gör det bättre eller sämre",
    "associated_symptoms": "Andra symtom", "previous_episodes": "Tidigare liknande besvär",
    "treatment_tried": "Behandling du redan provat", "injury_mechanism": "Skada eller vad som utlöste det",
    "radiation": "Om smärtan strålar ut", "intake_hydration": "Mat och dryck",
    "exposure_contacts": "Resor, mat eller sjuka i din omgivning", "sleep_pattern": "Sömn",
}

CATEGORY_SECTION = {"examination": "findings", "assessment": "assessment", "plan": "plan", "prescription": "plan",
                    "advice": "plan", "follow_up": "follow_up"}


def infer_section(facts: list[MedicalFact]) -> str:
    for f in facts:
        if f.category in CATEGORY_SECTION:
            return CATEGORY_SECTION[f.category]
    return "what_you_told"


def validate_patient_statements(output: PatientExplanationOutput, accepted_facts: list[MedicalFact],
                                language: str = "en") -> tuple[list[GeneratedStatement], list[ValidationFinding]]:
    by_id = {f.fact_id: f for f in accepted_facts}
    statements: list[GeneratedStatement] = []
    findings: list[ValidationFinding] = []
    for cand in output.statements:
        sid = f"P{len(statements) + 1:03d}"
        text = (cand.text or "").strip()
        if not text:
            continue
        ids = list(dict.fromkeys(cand.fact_ids))
        unknown = [f for f in ids if f not in by_id]
        if not ids or unknown:
            msg = ("A sentence was removed because it cited no facts." if not ids else
                   f"A sentence was removed because it cited unknown or unaccepted fact ID(s) {', '.join(unknown)}.")
            findings.append(ValidationFinding(code="statement_unknown_fact", severity="error", message=msg,
                                              ref_type="statement", ref_id=None))
            continue
        facts = [by_id[f] for f in ids]
        section = cand.section
        inferred = infer_section(facts)
        # Clinician facts must sit in a clinician section and vice versa.
        clinician = any(f.category in CLINICIAN_CATEGORIES for f in facts)
        if clinician != (section in {"findings", "assessment", "plan", "follow_up"}):
            section = inferred
        checks = fact_meaning_checks(text, facts, language)
        if checks:
            findings.append(ValidationFinding(code="possible_meaning_change", severity="warning",
                                              ref_type="statement", ref_id=sid,
                                              message=f"“{text[:90]}” — " + "; ".join(c.message for c in checks)))
        statements.append(GeneratedStatement(
            statement_id=sid, section=section, text=text, fact_ids=ids, needs_review=bool(checks),
            meaning_checks=checks, review_notes=["Possible meaning change — compare with the source."] if checks else []))
    return statements, findings


def build_plain_text(statements: list[GeneratedStatement], not_established: list[str], language: str,
                     patient_name: str | None, date_text: str) -> str:
    h = SECTION_HEADINGS["sv" if language == "sv" else "en"]
    title = "Sammanfattning av besöket" if language == "sv" else "After-visit summary"
    lines = [f"{title}{' — ' + patient_name if patient_name else ''} — {date_text}", ""]
    for section in SECTION_ORDER:
        items = [s.text for s in statements if s.section == section]
        if items:
            lines.append(h[section])
            lines += [f"• {t}" for t in items]
            lines.append("")
    if not_established:
        lines.append(h["not_established"])
        lines += [f"• {t}" for t in not_established]
        lines.append("")
    lines.append(DISCLAIMERS["sv" if language == "sv" else "en"])
    return "\n".join(lines).strip() + "\n"


# --------------------------------------------------------------------------- demo renderer (no LLM)

def _lower_first(text: str) -> str:
    text = text.strip().rstrip(".")
    return text[:1].lower() + text[1:] if text else text


def _plain(text: str) -> str:
    return simplify_text(text)[0]


def template_patient_explanation(facts: list[MedicalFact]) -> PatientExplanationOutput:
    """Deterministic rendering used by the demo provider (English only)."""
    statements: list[PatientStatementCandidate] = []
    chief = next((f for f in facts if f.category == "symptom" and f.polarity == "positive"), None)
    if chief:
        statements.append(PatientStatementCandidate(text=f"You came because of {_plain(chief.concept).lower()}.",
                                                    fact_ids=[chief.fact_id], section="your_concern"))
    clinician_intro = {"examination": "During the examination, your doctor said", "assessment": "Your doctor's view",
                       "plan": "Your doctor's plan", "prescription": "About medicine, your doctor said",
                       "advice": "Your doctor advised", "follow_up": "About follow-up, your doctor said"}
    for f in facts:
        concept = _plain(f.concept)
        section = "what_you_told"
        if f.category in CLINICIAN_CATEGORIES:
            section = CATEGORY_SECTION[f.category]
            sentence = _plain(f.normalized_value).strip().rstrip(".")
            text = f"{clinician_intro[f.category]}: {sentence}."
        elif f.polarity == "negative" and f.category == "medication":
            text = "You said you have not taken medication."
        elif f.polarity == "negative":
            text = f"You said you have not had {concept.lower()}."
        elif f.polarity == "uncertain":
            text = f"It was not clear from the conversation: {_lower_first(_plain(f.normalized_value))}."
        elif f.category == "symptom":
            details = [d for d in (f.duration, f.location, f.frequency, f.severity) if d]
            text = f"You told the doctor about your {concept.lower()}."
            if details:
                text += " Details you mentioned: " + "; ".join(f"“{d}”" for d in details) + "."
        elif f.category == "impact" and f.severity:
            text = f"You described how bad it was as “{f.severity}”."
        elif f.category == "medication":
            text = f"You mentioned taking {concept.lower()}."
        elif f.category in {"history", "allergy", "social"}:
            text = f"You mentioned: {_lower_first(_plain(f.normalized_value))}."
        else:
            text = f"It was noted that {_lower_first(_plain(f.normalized_value))}."
        statements.append(PatientStatementCandidate(text=text, fact_ids=[f.fact_id], section=section))  # type: ignore[arg-type]
    return PatientExplanationOutput(statements=statements)

