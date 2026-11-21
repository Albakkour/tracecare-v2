"""Deterministic validation of provider output against the transcript.

Important: a matching quote proves the text exists in the transcript. It does not prove the
clinical interpretation is correct. Results are labelled "source-linked" or "needs review", never
"clinically verified".
"""

from __future__ import annotations

import re

from app.llm.schemas import ChecklistCandidate, FactCandidate, SymptomCandidate
from app.schemas.coverage import ChecklistAssessment, ChecklistTemplate, ItemStatus
from app.schemas.facts import EvidenceReference, MedicalFact, SymptomMention
from app.schemas.outputs import ValidationFinding
from app.schemas.transcript import TranscriptSegment

FACT_ID_RE = re.compile(r"^F\d{3,}$")
PATIENT_SIDE = {"patient", "other"}

_CHAR_FOLD = str.maketrans({
    "‘": "'", "’": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ",
})


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace, fold quote/dash variants and case; keep a map back to original indices."""
    out: list[str] = []
    index_map: list[int] = []
    prev_space = False
    for i, ch in enumerate(text.translate(_CHAR_FOLD)):
        if ch.isspace():
            if prev_space or not out:
                continue
            out.append(" ")
            index_map.append(i)
            prev_space = True
        else:
            out.append(ch.lower())
            index_map.append(i)
            prev_space = False
    while out and out[-1] == " ":
        out.pop()
        index_map.pop()
    return "".join(out), index_map


def locate_quote(quote: str, segment: TranscriptSegment) -> EvidenceReference:
    """Find `quote` inside one segment: exact match first, whitespace/quote-normalized as fallback.

    The original quote string is always preserved in the returned reference.
    """
    stripped = quote.strip()
    if not stripped:
        return EvidenceReference(segment_id=segment.segment_id, speaker=segment.speaker, quote=quote,
                                 quote_match="not_found")
    idx = segment.text.find(stripped)
    if idx >= 0:
        start = segment.start_char + idx
        return EvidenceReference(segment_id=segment.segment_id, speaker=segment.speaker, quote=quote,
                                 quote_match="exact", start_char=start, end_char=start + len(stripped))
    norm_seg, seg_map = _normalize_with_map(segment.text)
    norm_quote, _ = _normalize_with_map(stripped)
    if norm_quote:
        nidx = norm_seg.find(norm_quote)
        if nidx >= 0:
            start = segment.start_char + seg_map[nidx]
            end = segment.start_char + seg_map[nidx + len(norm_quote) - 1] + 1
            return EvidenceReference(segment_id=segment.segment_id, speaker=segment.speaker, quote=quote,
                                     quote_match="normalized", start_char=start, end_char=end)
    return EvidenceReference(segment_id=segment.segment_id, speaker=segment.speaker, quote=quote,
                             quote_match="not_found")


def _locate_in_any(quote: str, segment_ids: list[str], seg_index: dict[str, TranscriptSegment]
                   ) -> tuple[list[EvidenceReference], list[str]]:
    """Locate a quote in any of the cited segments. Returns (evidence refs, unknown segment IDs)."""
    unknown = [sid for sid in segment_ids if sid not in seg_index]
    refs: list[EvidenceReference] = []
    for sid in dict.fromkeys(segment_ids):
        seg = seg_index.get(sid)
        if seg is None:
            continue
        ref = locate_quote(quote, seg)
        if ref.quote_match != "not_found":
            refs.append(ref)
            break
    return refs, unknown


# ----------------------------------------------------------------------------------------------
# Facts
# ----------------------------------------------------------------------------------------------

def validate_facts(candidates: list[FactCandidate], segments: list[TranscriptSegment]
                   ) -> tuple[list[MedicalFact], list[MedicalFact], list[ValidationFinding]]:
    """Return (usable facts, rejected facts, findings). Usable facts may be marked needs_review."""
    seg_index = {s.segment_id: s for s in segments}
    usable: list[MedicalFact] = []
    rejected: list[MedicalFact] = []
    findings: list[ValidationFinding] = []
    seen_ids: set[str] = set()

    for cand in candidates:
        notes: list[str] = []
        reject_reason: str | None = None
        needs_review = False

        if not FACT_ID_RE.match(cand.fact_id or ""):
            reject_reason = f"Malformed fact ID '{cand.fact_id}'."
        elif cand.fact_id in seen_ids:
            reject_reason = f"Duplicate fact ID '{cand.fact_id}'."
        seen_ids.add(cand.fact_id)

        quote = (cand.supporting_quote or "").strip()
        if not reject_reason and not quote:
            reject_reason = "Empty supporting quote."
        if not reject_reason and not (cand.concept or "").strip():
            reject_reason = "Empty concept."
        if not reject_reason and not (cand.normalized_value or "").strip():
            reject_reason = "Empty normalized value."

        evidence: list[EvidenceReference] = []
        valid_ids: list[str] = []
        if not reject_reason:
            refs, unknown = _locate_in_any(quote, cand.source_segment_ids, seg_index)
            valid_ids = [sid for sid in dict.fromkeys(cand.source_segment_ids) if sid in seg_index]
            if not cand.source_segment_ids:
                reject_reason = "No source segment IDs."
            elif not valid_ids:
                reject_reason = f"Unknown source segment ID(s): {', '.join(unknown)}."
            elif not refs:
                reject_reason = "Supporting quote does not appear in the referenced segment(s)."
            else:
                evidence = refs
                if unknown:
                    needs_review = True
                    notes.append(f"Removed unknown segment ID(s): {', '.join(unknown)}.")
                if refs[0].quote_match == "normalized":
                    notes.append("Quote matched after whitespace/punctuation normalization.")

        if reject_reason:
            fact = _to_fact(cand, cand.source_segment_ids or ["S000"], quote or "(empty)", "rejected",
                            [], [reject_reason])
            rejected.append(fact)
            findings.append(ValidationFinding(code="fact_rejected", severity="error", message=reject_reason,
                                              ref_type="fact", ref_id=cand.fact_id))
            continue

        # Speaker plausibility: patient-reported information should come from the patient side.
        speakers = {seg_index[sid].speaker for sid in valid_ids}
        quote_speaker = evidence[0].speaker
        if cand.category != "other":
            if not speakers & PATIENT_SIDE:
                needs_review = True
                if speakers == {"clinician"}:
                    msg = "Speaker mismatch: sourced only to clinician turn(s); the patient did not state this."
                else:
                    msg = "Speaker attribution unclear (unlabelled turn)."
                notes.append(msg)
                findings.append(ValidationFinding(code="speaker_mismatch", severity="warning", message=msg,
                                                  ref_type="fact", ref_id=cand.fact_id))
            elif quote_speaker == "clinician":
                notes.append("Quote is from a clinician question; the patient's answer is in a cited segment.")
            if speakers & PATIENT_SIDE == {"other"} and "patient" not in speakers:
                needs_review = True
                notes.append("Reported by someone other than the patient.")

        if cand.certainty != "explicit":
            needs_review = True
            notes.append(f"Certainty is '{cand.certainty}'; not presented as a confirmed fact.")

        status = "needs_review" if needs_review else "source_linked"
        if needs_review:
            findings.append(ValidationFinding(code="fact_needs_review", severity="warning",
                                              message="; ".join(notes) or "Needs review.",
                                              ref_type="fact", ref_id=cand.fact_id))
        usable.append(_to_fact(cand, valid_ids, quote, status, evidence, notes))

    return usable, rejected, findings


def _to_fact(cand: FactCandidate, segment_ids: list[str], quote: str, status: str,
             evidence: list[EvidenceReference], notes: list[str]) -> MedicalFact:
    def clean(v: str | None) -> str | None:
        return v.strip() if v and v.strip() else None

    return MedicalFact(
        fact_id=cand.fact_id if FACT_ID_RE.match(cand.fact_id or "") else "F000",
        category=cand.category,
        concept=(cand.concept or "").strip() or "(empty)",
        normalized_value=(cand.normalized_value or "").strip() or "(empty)",
        polarity=cand.polarity,
        certainty=cand.certainty,
        temporality=cand.temporality,
        duration=clean(cand.duration),
        frequency=clean(cand.frequency),
        severity=clean(cand.severity),
        location=clean(cand.location),
        context=clean(cand.context),
        source_segment_ids=segment_ids,
        supporting_quote=quote,
        evidence_status=status,  # type: ignore[arg-type]
        evidence=evidence,
        review_notes=notes,
    )


# ----------------------------------------------------------------------------------------------
# Symptom mentions
# ----------------------------------------------------------------------------------------------

def validate_symptoms(candidates: list[SymptomCandidate], segments: list[TranscriptSegment],
                      known_fact_ids: set[str], allowed_template_ids: set[str]
                      ) -> tuple[list[SymptomMention], list[ValidationFinding]]:
    seg_index = {s.segment_id: s for s in segments}
    mentions: list[SymptomMention] = []
    findings: list[ValidationFinding] = []
    for n, cand in enumerate(candidates, start=1):
        sid = f"SYM{n:02d}"
        notes: list[str] = []
        refs, unknown = _locate_in_any(cand.supporting_quote or "", cand.source_segment_ids, seg_index)
        if not refs:
            findings.append(ValidationFinding(
                code="symptom_rejected", severity="error", ref_type="symptom", ref_id=sid,
                message=f"Symptom '{cand.concept}' rejected: quote not found in referenced segment(s)."))
            continue
        status = "source_linked"
        if unknown:
            status = "needs_review"
            notes.append(f"Removed unknown segment ID(s): {', '.join(unknown)}.")
        fact_ids = [f for f in cand.fact_ids if f in known_fact_ids]
        if len(fact_ids) != len(cand.fact_ids):
            notes.append("Removed reference(s) to unknown or rejected fact IDs.")
        template_id = cand.template_id
        if template_id and template_id not in allowed_template_ids:
            findings.append(ValidationFinding(
                code="unknown_template", severity="error", ref_type="template", ref_id=template_id,
                message=f"Provider proposed a template that is not in the allowed registry: '{template_id}'."))
            template_id = None
            status = "needs_review"
        if refs[0].speaker not in PATIENT_SIDE:
            status = "needs_review"
            notes.append("Symptom mention not located in a patient turn.")
        mentions.append(SymptomMention(
            symptom_id=sid, concept=cand.concept.strip() or "(unnamed)", polarity=cand.polarity,
            fact_ids=fact_ids,
            source_segment_ids=[s for s in dict.fromkeys(cand.source_segment_ids) if s in seg_index],
            supporting_quote=cand.supporting_quote.strip(), template_id=template_id,
            evidence_status=status, evidence=refs, review_notes=notes))  # type: ignore[arg-type]
    return mentions, findings


# ----------------------------------------------------------------------------------------------
# Checklist assessments
# ----------------------------------------------------------------------------------------------

def derive_status(question_found: bool, information_found: bool) -> ItemStatus:
    if question_found and information_found:
        return "asked_and_addressed"
    if question_found:
        return "asked_but_unanswered"
    if information_found:
        return "volunteered_not_asked"
    return "not_found_in_transcript"


def _validate_evidence_list(segment_ids: list[str], quotes: list[str], expected_speakers: set[str],
                            role: str, seg_index: dict[str, TranscriptSegment]
                            ) -> tuple[list[EvidenceReference], list[str], bool]:
    """Validate question or information evidence. Returns (valid refs, notes, had_problem)."""
    refs: list[EvidenceReference] = []
    notes: list[str] = []
    problem = False
    unknown = [s for s in segment_ids if s not in seg_index]
    if unknown:
        problem = True
        notes.append(f"{role}: unknown segment ID(s) {', '.join(unknown)}.")
    known_ids = [s for s in dict.fromkeys(segment_ids) if s in seg_index]

    pending_quotes = [q for q in quotes if q and q.strip()]
    if not pending_quotes and known_ids:
        # No quote supplied: show the full original segment text (it is exact by construction).
        pending_quotes = [seg_index[s].text for s in known_ids]
        notes.append(f"{role}: no quote supplied; full segment text shown.")
    elif pending_quotes and not known_ids:
        problem = True
        notes.append(f"{role}: quote(s) given without a valid segment ID.")

    for q in pending_quotes:
        found, _ = _locate_in_any(q, known_ids, seg_index)
        if not found:
            problem = True
            notes.append(f"{role}: quote not found in cited segment(s): \"{q[:80]}\".")
            continue
        ref = found[0]
        if ref.speaker not in expected_speakers:
            problem = True
            who = "unlabelled" if ref.speaker == "unknown" else ref.speaker
            notes.append(f"{role}: speaker mismatch — evidence {ref.segment_id} is a {who} turn.")
            continue
        refs.append(ref)
    return refs, notes, problem


def validate_checklist(candidates: list[ChecklistCandidate], template: ChecklistTemplate,
                       segments: list[TranscriptSegment], known_fact_ids: set[str]
                       ) -> tuple[list[ChecklistAssessment], list[ValidationFinding]]:
    seg_index = {s.segment_id: s for s in segments}
    findings: list[ValidationFinding] = []
    by_item: dict[str, ChecklistCandidate] = {}
    valid_items = template.item_ids()

    for cand in candidates:
        if cand.template_id != template.template_id:
            continue
        if cand.item_id not in valid_items:
            findings.append(ValidationFinding(
                code="unknown_checklist_item", severity="error", ref_type="checklist_item", ref_id=cand.item_id,
                message=f"Provider proposed checklist item '{cand.item_id}', which is not in "
                        f"{template.template_id}; it was ignored."))
            continue
        if cand.item_id in by_item:
            findings.append(ValidationFinding(
                code="duplicate_checklist_item", severity="warning", ref_type="checklist_item",
                ref_id=cand.item_id, message=f"Duplicate assessment for '{cand.item_id}'; the first was kept."))
            continue
        by_item[cand.item_id] = cand

    assessments: list[ChecklistAssessment] = []
    for item in template.items:
        cand = by_item.get(item.item_id)
        if cand is None:
            assessments.append(ChecklistAssessment(
                item_id=item.item_id, label=item.label, status="not_found_in_transcript",
                review_state="provisional",
                validation_notes=["No relevant question or information was identified. Provisional until reviewed."]))
            continue

        q_refs, q_notes, q_problem = _validate_evidence_list(
            cand.clinician_question_segment_ids, cand.clinician_question_quotes, {"clinician"},
            "Clinician question", seg_index)
        i_refs, i_notes, i_problem = _validate_evidence_list(
            cand.information_segment_ids, cand.information_quotes, PATIENT_SIDE,
            "Information", seg_index)
        notes = q_notes + i_notes
        fact_ids = [f for f in dict.fromkeys(cand.fact_ids) if f in known_fact_ids]
        if len(fact_ids) != len(set(cand.fact_ids)):
            notes.append("Removed reference(s) to unknown or rejected fact IDs.")

        derived = derive_status(bool(q_refs), bool(i_refs))
        proposed = cand.proposed_status
        status: ItemStatus = derived
        review_state = "provisional"
        if proposed == "not_applicable":
            status, review_state = "unclear_needs_review", "needs_review"
            notes.append("Only a human reviewer can mark an item not applicable.")
        elif proposed == "unclear_needs_review":
            status, review_state = "unclear_needs_review", "needs_review"
            notes.append("Provider marked this item unclear.")
        elif derived == "not_found_in_transcript" and not (q_problem or i_problem) \
                and proposed == "not_found_in_transcript":
            # Absence of evidence is the gap the metric must show: keep it in the denominator
            # (provisional) even if the provider was unsure, instead of hiding it as "pending".
            status, review_state = "not_found_in_transcript", "provisional"
            if cand.confidence == "low":
                notes.append("Provider was unsure; kept as not found (counted) — please review.")
        elif cand.confidence == "low":
            status, review_state = "unclear_needs_review", "needs_review"
            notes.append("Low-confidence mapping: excluded from the denominator until reviewed.")
        elif q_problem or i_problem:
            status, review_state = "unclear_needs_review", "needs_review"
        elif derived != proposed:
            status, review_state = "unclear_needs_review", "needs_review"
            notes.append(f"Provider proposed '{proposed}' but validated evidence supports '{derived}'.")

        if status == "unclear_needs_review":
            findings.append(ValidationFinding(
                code="checklist_needs_review", severity="warning", ref_type="checklist_item",
                ref_id=f"{template.template_id}:{item.item_id}",
                message=f"{item.label}: " + ("; ".join(notes) or "needs review.")))
        if status == "not_found_in_transcript":
            notes.append("Not found in transcript — provisional until reviewed.")

        assessments.append(ChecklistAssessment(
            item_id=item.item_id, label=item.label, status=status,
            clinician_question_segment_ids=[r.segment_id for r in q_refs],
            clinician_question_quotes=[r.quote for r in q_refs],
            information_segment_ids=[r.segment_id for r in i_refs],
            information_quotes=[r.quote for r in i_refs],
            question_evidence=q_refs, information_evidence=i_refs, fact_ids=fact_ids,
            proposed_status=proposed, rationale=(cand.rationale or None),
            review_state=review_state, validation_notes=notes))  # type: ignore[arg-type]
    return assessments, findings


# ----------------------------------------------------------------------------------------------
# Generated statements
# ----------------------------------------------------------------------------------------------

def unknown_fact_ids(fact_ids: list[str], known_fact_ids: set[str]) -> list[str]:
    return [f for f in fact_ids if f not in known_fact_ids]
