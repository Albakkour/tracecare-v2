"""Deterministic, rule-based demo provider. No AI, no network, no API credits.

It uses small keyword lexicons to propose candidate facts and checklist evidence so the full
TraceCare pipeline can be demonstrated and tested offline. Its output is clearly labelled and goes
through exactly the same validation as the Claude provider's output. It is intentionally simple
and will miss or misread things that a clinician (or a stronger model) would not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.llm.schemas import (
    ChecklistCandidate,
    ExtractionOutput,
    FactCandidate,
    PatientExplanationOutput,
    SymptomCandidate,
)
from app.schemas.coverage import ChecklistTemplate
from app.schemas.facts import MedicalFact
from app.schemas.transcript import TranscriptSegment
from app.services.evidence_validator import derive_status
from app.services.patient_explainer import template_patient_explanation

I = re.IGNORECASE
NUM = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|a few|a couple of|several)"

SYMPTOMS: list[tuple[str, re.Pattern[str]]] = [
    ("headache", re.compile(r"\b(headaches?|migraines?|head (?:hurts|pain|ache)|head (?:has been |is )?(?:pounding|hurting|aching|throbbing))\b", I)),
    ("fever", re.compile(r"\b(fevers?|feverish|(?:a |slight |high )temperature)\b", I)),
    ("dizziness", re.compile(r"\b(dizzy|dizziness|light-?headed)\b", I)),
    ("nausea", re.compile(r"\b(nausea|nauseous|nauseated|sick to my stomach|fe(?:lt|el) sick)\b", I)),
    ("vomiting", re.compile(r"\b(vomit\w*|throwing up|threw up)\b", I)),
    ("visual changes", re.compile(r"\b(blurr?(?:y|ed) vision|vision changes|visual changes|double vision|"
                                  r"spots in (?:my|your) vision|wavy lines)\b", I)),
    ("light sensitivity", re.compile(r"\b(sensitiv\w* to (?:the )?light|bright lights?|photophobia)\b", I)),
    ("ringing in the ears", re.compile(r"\b(ringing in (?:my|your|the) ears?|tinnitus)\b", I)),
    ("numbness or tingling", re.compile(r"\b(numb\w*|tingl\w*|pins and needles)\b", I)),
    ("neck stiffness", re.compile(r"\b(stiff neck|neck stiffness)\b", I)),
    ("back pain", re.compile(r"\b(back pain|(?:lower|low|my) back)\b", I)),
    ("knee pain", re.compile(r"\b(knee pain|my knee|(?:right|left) knee)\b", I)),
    ("shoulder pain", re.compile(r"\b(shoulder pain|my shoulder)\b", I)),
    ("neck pain", re.compile(r"\bneck pain\b", I)),
    ("cough", re.compile(r"\b(cough\w*)\b", I)),
    ("shortness of breath", re.compile(r"\b(short(?:ness)? of breath|breathless\w*|trouble breathing)\b", I)),
    ("chest pain", re.compile(r"\bchest pain\b", I)),
    ("fatigue", re.compile(r"\b(fatigue\w*|exhausted)\b", I)),
    ("sore throat", re.compile(r"\bsore throat\b", I)),
    ("rash", re.compile(r"\brash\b", I)),
]

QUESTION_RE = re.compile(
    r"\?|^\s*(?:okay|ok|alright|and|so|um|uh|now|hmm+)?[\s,]*(?:have|has|do|does|did|is|are|was|were|can|could|"
    r"would|will|when|where|how|what|which|why|any)\b|\b(?:have you|do you|did you|are you|is it|does it|any)\b", I)
NEG_RE = re.compile(r"\b(no|not|never|none|without|denies|denied|nothing)\b|n't\b|n['’]t\b|\bn ?'t\b", I)
UNCERTAIN_RE = re.compile(r"\b(not sure|unsure|maybe|i think|i guess|might|(?:do|ca)\s*n['’]?t (?:remember|recall|know)|"
                          r"don['’]t (?:remember|know)|can['’]t (?:remember|recall)|forgot|no idea)\b", I)
NON_ANSWER_RE = re.compile(r"^\W*(?:i\s+)?(?:do\s*n['’]?t|do not|ca\s*n['’]?t|cannot|can not)\s+(?:really\s+)?"
                           r"(?:know|remember|recall|say|tell)|^\W*(?:i'?m\s+)?not sure|^\W*no idea|^\W*(?:hmm+|um+|uh+)\W*$", I)
YES_RE = re.compile(r"^\W*(?:yes|yeah|yep|yup|i have|i do|i did|correct|that's right|sometimes|a little)\b", I)
NO_RE = re.compile(r"^\W*(?:no|nope|not really|never|nah|i have\s*n['’]?t|i haven't|i don['’]?t|i do not)\b", I)

DURATION_RE = re.compile(rf"\b((?:for |about |almost |nearly |over |the past |the last )?{NUM}\s+(?:days?|weeks?|months?|years?|hours?)"
                         r"(?: ago| now)?|since (?:yesterday|last \w+|this morning|monday|tuesday|wednesday|thursday|friday|"
                         r"saturday|sunday)|yesterday|this morning|last night)\b", I)
LOCATION_RE = re.compile(r"\b(on (?:my|the) (?:right|left) side|(?:right|left)[- ]sided|behind my (?:right |left )?eyes?|"
                         r"(?:the )?back of my head|(?:the )?front of my head|forehead|temples?|lower back|low back|"
                         r"(?:right|left) (?:knee|shoulder|hip|ankle|side))\b", I)
DESCRIPTION_RE = re.compile(r"\b(dull|sharp|throbbing|pulsing|pounding|stabbing|aching|burning|pressure|tight\w*|squeezing|"
                            r"shooting)\b", I)
FREQUENCY_RE = re.compile(r"\b(every day|daily|every (?:morning|night|evening)|(?:once|twice|\w+ times) a (?:day|week|month)|"
                          r"comes and goes|constant(?:ly)?|all the time|on and off|sometimes|occasionally|"
                          r"more frequent(?:ly)?)\b", I)
SEVERITY_RE = re.compile(r"\b((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten) out of (?:10|ten)|mild|moderate|severe|"
                         r"really bad|worst)\b", I)
MED_RE = re.compile(r"\b(ibuprofen|advil|motrin|tylenol|paracetamol|acetaminophen|aspirin|naproxen|aleve|excedrin|"
                    r"sumatriptan|imitrex|metformin|lisinopril|painkillers?|pain killers?|pain medication|medications?|"
                    r"medicines?|pills?|tablets?)\b", I)
GENERIC_MED = {"painkiller", "painkillers", "pain killer", "pain killers", "pain medication", "medication", "medications",
               "medicine", "medicines", "pill", "pills", "tablet", "tablets"}
DOSE_UNCERTAIN_RE = re.compile(r"(?:do\s*n['’]?t|do not|ca\s*n['’]?t|cannot|not sure|does\s*n['’]?t|forgot|forget)[^.?!]{0,40}"
                               r"(?:dose|dosage|how much|how many|milligram|mg\b|strength)", I)
HISTORY_RE = re.compile(r"\b((?:had|have had|gotten|get) (?:this|these|it|them|one|something like this|headaches like this)"
                        r" before|ever since|for years|history of)\b", I)
ALLERGY_RE = re.compile(r"\ballergic to ([a-z][a-z ]{1,30})", I)
NO_ALLERGY_RE = re.compile(r"\bno (?:known )?allergies\b", I)
FIRST_PERSON_RE = re.compile(r"\b(i|i'm|i've|i'd|my|me)\b", I)
ACK_RE = re.compile(r"^\W*(?:(?:yeah|yes|okay|ok|alright|sure|great)\W*)*(?:that sounds|sounds (?:good|great)|thanks?\b|"
                    r"thank you|okay\W*$|ok\W*$|alright\W*$|sure\W*$|bye)", I)
# Long clinician turns are usually examination findings or plans, not questions.
MAX_QUESTION_TURN_CHARS = 400

_BASE = {
    "triggers": r"worse when|worse with|better when|better with|\bhelps?\b|helped|reliev\w*|trigger\w*|"
                r"when i(?:'m)? (?:exercis|stress|jog|run|bend|stand|sit|lie|lay)|stress\w*|exercis\w*",
}

ITEM_CUES: dict[str, dict[str, tuple[str, re.Pattern[str] | str]]] = {
    "headache_demo_v1": {
        "onset": (r"when did|\bstart|\bbegin|\bbegan|first notice|all of a sudden|sudden|gradual",
                  re.compile(r"\bstarted\b|\bbegan\b|\bago\b|\bsince\b|yesterday|this morning|last night|suddenly|"
                             r"gradual|all of a sudden", I)),
        "duration_course": (r"how long|constant|come and go|comes and goes|changed|getting (?:worse|better)",
                            re.compile(DURATION_RE.pattern + r"|comes and goes|constant|getting (?:worse|better)|"
                                       r"more frequent", I)),
        "location": (r"\bwhere\b|which side|what part", LOCATION_RE),
        "description": (r"describe|feel like|how do(?:es)? (?:it|they) feel|what kind of|what type of", DESCRIPTION_RE),
        "severity_impact": (r"how (?:bad|severe|strong)|scale|out of (?:10|ten)|\brate\b|affect|interfer|prevent|stop you",
                            re.compile(SEVERITY_RE.pattern + r"|ca\s*n['’]?t (?:work|sleep|exercise)|miss(?:ed)? work|"
                                       r"prevented", I)),
        "frequency_pattern": (r"how often|how many times|how frequent|every day|time of (?:the )?day|worse in the|pattern",
                              re.compile(FREQUENCY_RE.pattern + r"|in the (?:morning|evening)|at night", I)),
        "triggers_relief": (r"better or worse|worse or better|makes? (?:it|them|the pain) (?:better|worse)|trigger|(?:anything|that|it) help|reliev|activit",
                            re.compile(_BASE["triggers"], I)),
        "other_symptoms": (r"anything else|other symptoms|any other|along with", "OTHER_SYMPTOMS"),
    },
    "msk_pain_demo_v1": {
        "onset": (r"when did|\bstart|\bbegin|\bbegan|how long have|first notice",
                  re.compile(r"\bstarted\b|\bbegan\b|\bago\b|\bsince\b|yesterday|this morning|last (?:week|night|month)", I)),
        "injury_mechanism": (r"injur|accident|\bfall\b|\bfell\b|what happened|how did (?:it|this) happen|what were you doing",
                             re.compile(r"\bfell\b|lifting|twisted|injur\w*|accident\w*|raking|playing|no,? i haven", I)),
        "location": (r"\bwhere\b|which side|what part|point to", LOCATION_RE),
        "description": (r"describe|feel like|what kind of|what type of", DESCRIPTION_RE),
        "severity_impact": (r"how (?:bad|severe|strong)|scale|out of (?:10|ten)|\brate\b|affect|interfer|prevent|stop you",
                            re.compile(SEVERITY_RE.pattern + r"|ca\s*n['’]?t (?:work|sleep|walk)|miss(?:ed)? work", I)),
        "aggravating_relieving": (r"better or worse|worse or better|makes? (?:it|them|the pain) (?:better|worse)|"
                                  r"(?:anything|that|it) help|when you(?:'re)? (?:laying|lying|sitting|standing)", re.compile(_BASE["triggers"] + r"|hurts (?:more|less) when", I)),
        "previous_episodes": (r"before|in the past|ever had", re.compile(HISTORY_RE.pattern + r"|once about|last time", I)),
        "treatment_tried": (r"\btried\b|\btaken\b|take anything|medication|\bice\b|icing|\bheat\b", re.compile(MED_RE.pattern + r"|\bice\b|"
                            r"icing|heat|hot shower|physical therapy|stretch\w*", I)),
        "other_symptoms": (r"anything else|other symptoms|any other|numbness|tingling", "OTHER_SYMPTOMS"),
    },
}


@dataclass
class _Builder:
    segments: list[TranscriptSegment]
    facts: list[FactCandidate] = field(default_factory=list)
    keys: set[tuple[str, str]] = field(default_factory=set)

    def add(self, key: tuple[str, str], **kwargs) -> None:
        if key in self.keys:
            return
        self.keys.add(key)
        self.facts.append(FactCandidate(fact_id=f"F{len(self.facts) + 1:03d}", **kwargs))


def _sentences(text: str) -> list[tuple[int, int]]:
    spans = [(m.start(), m.end()) for m in re.finditer(r"[^.!?]+[.!?]*", text)]
    return spans or [(0, len(text))]


def _window(text: str, start: int, end: int, radius: int = 110) -> str:
    """Exact substring of `text` around [start, end): the containing sentence, trimmed if long."""
    for s, e in _sentences(text):
        if s <= start < e:
            if e - s <= 2 * radius + (end - start):
                return text[s:e].strip()
            ws = max(s, start - radius)
            we = min(e, end + radius)
            while ws > s and not text[ws - 1].isspace():
                ws += 1
            while we < e and not text[we].isspace():
                we += 1
            return text[ws:we].strip()
    return text.strip()


def _clause_prefix(text: str, pos: int) -> str:
    """Text from the start of the current clause up to `pos` (for negation scope)."""
    boundary = max(text.rfind(ch, 0, pos) for ch in ".!?;,")
    but = max(text.lower().rfind(" but ", 0, pos), text.lower().rfind(" and ", 0, pos))
    return text[max(boundary, but) + 1:pos]


def _clean_duration(value: str | None) -> str | None:
    return re.sub(r"^for\s+", "", value, flags=I) if value else None


def _first_sentence(text: str) -> str:
    s, e = _sentences(text)[0]
    return _window(text, s, min(e, s + 1))


def _question_cue(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    """Return a cue match only if it sits inside a sentence that reads as a question."""
    if len(text) > MAX_QUESTION_TURN_CHARS:
        return None
    for s, e in _sentences(text):
        m = pattern.search(text, s, e)
        if m and QUESTION_RE.search(text[s:e]):
            return m
    return None


def _near(pattern: re.Pattern[str], text: str, start: int, end: int, radius: int = 60) -> str | None:
    """A detail (duration, location...) mentioned close to the symptom, within the same sentence."""
    for s, e in _sentences(text):
        if s <= start < e:
            m = pattern.search(text, max(s, start - radius), min(e, end + radius))
            return m.group(0).strip() if m else None
    return None


def _symptom_matches(text: str) -> list[tuple[str, re.Match[str]]]:
    hits = []
    for concept, pattern in SYMPTOMS:
        hits.extend((concept, m) for m in pattern.finditer(text))
    return sorted(hits, key=lambda h: h[1].start())


def _in_sentence(pattern: re.Pattern[str], text: str, pos: int) -> str | None:
    for s, e in _sentences(text):
        if s <= pos < e:
            m = pattern.search(text, s, e)
            return m.group(0).strip() if m else None
    return None


class DemoProvider:
    name = "demo"
    label = "Demo provider (rule-based, deterministic — not AI)"
    model: str | None = None

    # ------------------------------------------------------------------ facts
    def _extract_facts(self, segments: list[TranscriptSegment]) -> list[FactCandidate]:
        b = _Builder(segments)
        positive_concepts: set[str] = set()
        for idx, seg in enumerate(segments):
            text = seg.text
            if seg.speaker in {"patient", "other", "unknown"}:
                self._patient_symptoms(b, seg, positive_concepts)
                self._patient_medications(b, seg)
                self._patient_history(b, seg)
            elif seg.speaker == "clinician" and len(text) <= MAX_QUESTION_TURN_CHARS and QUESTION_RE.search(text):
                nxt = segments[idx + 1] if idx + 1 < len(segments) else None
                if nxt is not None and nxt.speaker in {"patient", "other"}:
                    self._question_answer(b, seg, nxt, positive_concepts)
        return b.facts

    def _patient_symptoms(self, b: _Builder, seg: TranscriptSegment, positive: set[str]) -> None:
        text = seg.text
        for concept, m in _symptom_matches(text):
            prefix = _clause_prefix(text, m.start())
            quote = _window(text, m.start(), m.end())
            if UNCERTAIN_RE.search(quote) and not NEG_RE.search(prefix):
                polarity, value = "uncertain", f"{concept.capitalize()} mentioned with uncertainty"
            elif NEG_RE.search(prefix):
                polarity, value = "negative", f"No {concept} reported"
            else:
                polarity, value = "positive", concept.capitalize()
                positive.add(concept)
            if polarity == "negative" and concept in positive:
                continue  # keep the demo conservative: do not add a contradicting negative
            b.add((concept, polarity), category="symptom", concept=concept, normalized_value=value,
                  polarity=polarity, certainty="explicit", temporality="current",
                  duration=_clean_duration(_near(DURATION_RE, text, m.start(), m.end())) if polarity == "positive" else None,
                  frequency=_near(FREQUENCY_RE, text, m.start(), m.end()) if polarity == "positive" else None,
                  severity=_near(SEVERITY_RE, text, m.start(), m.end()) if polarity == "positive" else None,
                  location=_near(LOCATION_RE, text, m.start(), m.end()) if polarity == "positive" else None,
                  source_segment_ids=[seg.segment_id], supporting_quote=quote)
        sev = SEVERITY_RE.search(text)
        if sev and re.search(r"out of", sev.group(0), I) and not _symptom_matches(text):
            b.add(("severity", sev.group(0).lower()), category="impact", concept="severity rating",
                  normalized_value=f"Severity rated {sev.group(0)}", polarity="positive", certainty="explicit",
                  temporality="current", severity=sev.group(0), source_segment_ids=[seg.segment_id],
                  supporting_quote=_window(text, sev.start(), sev.end()))

    def _patient_medications(self, b: _Builder, seg: TranscriptSegment) -> None:
        text = seg.text
        dose = DOSE_UNCERTAIN_RE.search(text)
        if dose:
            b.add(("medication dosage", "uncertain"), category="medication", concept="medication dosage",
                  normalized_value="Medication dosage not remembered", polarity="uncertain", certainty="explicit",
                  temporality="current", source_segment_ids=[seg.segment_id],
                  supporting_quote=_window(text, dose.start(), dose.end()))
        matches = list(MED_RE.finditer(text))
        if not matches:
            return
        names = list(dict.fromkeys(m.group(0).lower() for m in matches if m.group(0).lower() not in GENERIC_MED))
        first = matches[0]
        if NEG_RE.search(_clause_prefix(text, first.start())) and not names:
            b.add(("medication", "negative"), category="medication", concept="medication",
                  normalized_value="No medication taken", polarity="negative", certainty="explicit",
                  temporality="current", source_segment_ids=[seg.segment_id],
                  supporting_quote=_window(text, first.start(), first.end()))
            return
        if names:
            b.add(("medication:" + ",".join(names), "positive"), category="medication", concept=", ".join(names),
                  normalized_value=f"Has taken {', '.join(names)}", polarity="positive", certainty="explicit",
                  temporality="current", source_segment_ids=[seg.segment_id],
                  supporting_quote=_window(text, first.start(), matches[-1].end()))

    def _patient_history(self, b: _Builder, seg: TranscriptSegment) -> None:
        text = seg.text
        m = HISTORY_RE.search(text)
        if m:
            neg = bool(NEG_RE.search(_clause_prefix(text, m.start())))
            b.add(("history", "negative" if neg else "positive"), category="history", concept="previous episodes",
                  normalized_value="No similar episodes before" if neg else "Similar episodes before",
                  polarity="negative" if neg else "positive", certainty="explicit", temporality="historical",
                  source_segment_ids=[seg.segment_id], supporting_quote=_window(text, m.start(), m.end()))
        a = ALLERGY_RE.search(text)
        if a:
            b.add(("allergy", a.group(1)), category="allergy", concept="allergy",
                  normalized_value=f"Allergic to {a.group(1).strip()}", polarity="positive", certainty="explicit",
                  temporality="current", source_segment_ids=[seg.segment_id],
                  supporting_quote=_window(text, a.start(), a.end()))
        na = NO_ALLERGY_RE.search(text)
        if na:
            b.add(("allergy", "negative"), category="allergy", concept="allergies", normalized_value="No allergies reported",
                  polarity="negative", certainty="explicit", temporality="current",
                  source_segment_ids=[seg.segment_id], supporting_quote=_window(text, na.start(), na.end()))

    def _question_answer(self, b: _Builder, q: TranscriptSegment, a: TranscriptSegment, positive: set[str]) -> None:
        """Short yes/no answers to a clinician question (the answer itself names nothing)."""
        answer = a.text
        if _symptom_matches(answer) or MED_RE.search(answer) or ACK_RE.search(answer):
            return  # the patient branch already handles answers that name the topic
        yes, no = bool(YES_RE.search(answer)), bool(NO_RE.search(answer))
        if yes == no:
            return
        quote = _first_sentence(answer)
        ids = [q.segment_id, a.segment_id]
        hits = _symptom_matches(q.text)
        if hits:
            concept = hits[0][0]
            if no and concept not in positive:
                b.add((concept, "negative"), category="symptom", concept=concept, normalized_value=f"No {concept} reported",
                      polarity="negative", certainty="explicit", temporality="current",
                      source_segment_ids=ids, supporting_quote=quote)
            elif yes:
                positive.add(concept)
                b.add((concept, "positive"), category="symptom", concept=concept,
                      normalized_value=concept.capitalize(), polarity="positive", certainty="explicit",
                      temporality="current", source_segment_ids=ids,
                      supporting_quote=quote)
            return
        med = MED_RE.search(q.text) or re.search(r"\b(?:taken|take|tried) anything\b", q.text, I)
        if med and re.search(r"allerg|condition|history", q.text, I):
            med = None  # "medication allergies?" / "medical conditions?" — a "no" is not "no medication"
        if med:
            if yes:
                b.add(("medication", "positive"), category="medication", concept="medication",
                      normalized_value="Has taken medication (name unspecified)", polarity="positive",
                      certainty="explicit", temporality="current",
                      source_segment_ids=ids, supporting_quote=quote)
            elif not any(f.category == "medication" and f.polarity == "positive" for f in b.facts):
                b.add(("medication", "negative"), category="medication", concept="medication",
                      normalized_value="No medication taken", polarity="negative", certainty="explicit",
                      temporality="current", source_segment_ids=ids,
                      supporting_quote=quote)
            return
        if re.search(r"\bbefore\b", q.text, I) and re.search(r"\b(had|ever|experienced)\b", q.text, I):
            b.add(("history", "positive" if yes else "negative"), category="history", concept="previous episodes",
                  normalized_value="Similar episodes before" if yes else "No similar episodes before",
                  polarity="positive" if yes else "negative", certainty="explicit", temporality="historical",
                  source_segment_ids=ids, supporting_quote=quote)

    # ------------------------------------------------------------- checklist
    def _assess(self, template: ChecklistTemplate, segments: list[TranscriptSegment], facts: list[FactCandidate],
                primary_concepts: set[str]) -> list[ChecklistCandidate]:
        cues = ITEM_CUES.get(template.template_id)
        if not cues:
            return []
        out: list[ChecklistCandidate] = []
        for item in template.items:
            if item.item_id not in cues:
                continue
            q_pattern, info = cues[item.item_id]
            q_re = re.compile(q_pattern, I)

            def info_match(text: str):
                if info == "OTHER_SYMPTOMS":
                    for concept, m in _symptom_matches(text):
                        if concept not in primary_concepts:
                            return m
                    return None
                return info.search(text)  # type: ignore[union-attr]

            def mentions_primary(text: str) -> bool:
                return any(c in primary_concepts for c, _ in _symptom_matches(text)) or bool(
                    re.search(r"\b(pain|hurts?|ache)\b", text, I))

            q_refs: list[tuple[str, str]] = []
            i_refs: list[tuple[str, str]] = []
            answered_ids: set[str] = set()
            unanswered = False
            for idx, seg in enumerate(segments):
                if seg.speaker != "clinician":
                    continue
                qm = _question_cue(q_re, seg.text)
                if qm is None and info == "OTHER_SYMPTOMS" and len(seg.text) <= MAX_QUESTION_TURN_CHARS:
                    om = info_match(seg.text)
                    qm = om if om and QUESTION_RE.search(seg.text) else None
                if not qm:
                    continue
                nxt = segments[idx + 1] if idx + 1 < len(segments) else None
                if not q_refs:
                    q_refs.append((seg.segment_id, _window(seg.text, qm.start(), qm.end())))
                if nxt is None or nxt.speaker not in {"patient", "other"}:
                    continue
                answered_ids.add(nxt.segment_id)
                if ACK_RE.search(nxt.text):
                    continue
                if NON_ANSWER_RE.search(nxt.text):
                    unanswered = True
                    continue
                if not i_refs:
                    if q_refs[0][0] != seg.segment_id:
                        q_refs = [(seg.segment_id, _window(seg.text, qm.start(), qm.end()))]
                    im = info_match(nxt.text)
                    i_refs.append((nxt.segment_id, _window(nxt.text, im.start(), im.end()) if im
                                   else _first_sentence(nxt.text)))
            if not i_refs:
                for seg in segments:
                    if seg.speaker in {"patient", "other"} and seg.segment_id not in answered_ids:
                        if info != "OTHER_SYMPTOMS" and not mentions_primary(seg.text):
                            continue
                        im = info_match(seg.text)
                        if im:
                            i_refs.append((seg.segment_id, _window(seg.text, im.start(), im.end())))
                            break

            proposed = derive_status(bool(q_refs), bool(i_refs))
            rationale = "Rule-based keyword match (demo provider)."
            if proposed == "asked_but_unanswered" and not unanswered:
                rationale = "Clinician question found; no usable answer identified (demo provider)."
            if proposed == "not_found_in_transcript":
                # Possible speaker-label problem: first-person information inside clinician-labelled turns.
                for seg in segments:
                    im = info_match(seg.text) if seg.speaker == "clinician" else None
                    if im and FIRST_PERSON_RE.search(seg.text) and not QUESTION_RE.search(seg.text[:40]):
                        i_refs = [(seg.segment_id, _window(seg.text, im.start(), im.end()))]
                        proposed = "unclear_needs_review"
                        rationale = ("Relevant first-person information appears in a clinician-labelled turn; "
                                     "speaker labels may be wrong (demo provider).")
                        break
                else:
                    continue
            info_ids = {sid for sid, _ in i_refs}
            out.append(ChecklistCandidate(
                template_id=template.template_id, item_id=item.item_id, proposed_status=proposed,
                clinician_question_segment_ids=[s for s, _ in q_refs], clinician_question_quotes=[q for _, q in q_refs],
                information_segment_ids=[s for s, _ in i_refs], information_quotes=[q for _, q in i_refs],
                fact_ids=[f.fact_id for f in facts if info_ids & set(f.source_segment_ids)],
                confidence="high", rationale=rationale))
        return out

    # --------------------------------------------------------------- public
    def extract(self, segments: list[TranscriptSegment], templates: list[ChecklistTemplate]) -> ExtractionOutput:
        facts = self._extract_facts(segments)
        symptoms: list[SymptomCandidate] = []
        checklist: list[ChecklistCandidate] = []
        used_templates: set[str] = set()
        for f in facts:
            if f.category != "symptom":
                continue
            template_id = None
            if f.polarity == "positive":
                for t in templates:
                    if any(tc in f.concept or f.concept in tc for tc in t.trigger_concepts):
                        template_id = t.template_id
                        break
            symptoms.append(SymptomCandidate(concept=f.concept, polarity=f.polarity, fact_ids=[f.fact_id],
                                             source_segment_ids=f.source_segment_ids,
                                             supporting_quote=f.supporting_quote, template_id=template_id))
            if template_id and template_id not in used_templates:
                used_templates.add(template_id)
                t = next(t for t in templates if t.template_id == template_id)
                primary = {f.concept} | {c for c, _ in SYMPTOMS if any(c in tc or tc in c for tc in t.trigger_concepts)}
                checklist.extend(self._assess(t, segments, facts, primary))
        return ExtractionOutput(facts=facts, symptoms=symptoms, checklist_assessments=checklist)

    def explain_for_patient(self, facts: list[MedicalFact], language: str) -> PatientExplanationOutput:
        return template_patient_explanation(facts)
