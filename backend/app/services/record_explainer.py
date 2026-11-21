"""Record explainer (hackathon idea 5): clinical note → plain language, sentence by sentence.

Every plain sentence cites the original sentence IDs; deterministic checks flag where meaning may have changed
(lost/added negation, lost hedge, missing/changed number). Original sentences that no plain sentence covers are
reported, because dropped content is a meaning change too.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.llm.base import LLMProvider
from app.schemas.records import PlainStatement, RecordExplainResponse, RecordSentence
from app.services.meaning import risk_level, text_meaning_checks
from app.services.plain_language import simplify_text
from app.services.transcript_parser import normalize_line_endings

_SENTENCE_RE = re.compile(r"(?:[^.!?\n]|\.(?=\d))+[.!?]*")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def _is_heading(line: str) -> bool:
    t = line.strip()
    if not t or len(t) > 60:
        return False
    letters = [c for c in t if c.isalpha()]
    return (t.endswith(":") and len(t.split()) <= 6) or (bool(letters) and t.isupper() and not t.endswith("."))


def split_record(text: str) -> list[RecordSentence]:
    normalized = normalize_line_endings(text)
    sentences: list[RecordSentence] = []
    heading: str | None = None
    offset = 0
    for line in normalized.split("\n"):
        line_start = offset
        offset += len(line) + 1
        if not line.strip():
            continue
        if _is_heading(line):
            heading = line.strip().rstrip(":").title()
            continue
        body_start = _BULLET_RE.match(line).end() if _BULLET_RE.match(line) else 0
        for m in _SENTENCE_RE.finditer(line, body_start):
            raw = m.group(0)
            stripped = raw.strip()
            if len(stripped) < 2:
                continue
            start = line_start + m.start() + (len(raw) - len(raw.lstrip()))
            sentences.append(RecordSentence(sentence_id=f"R{len(sentences) + 1:03d}", text=stripped, start_char=start,
                                            end_char=start + len(stripped), heading=heading))
    return sentences


def build_record_plain_text(sentences: list[RecordSentence], statements: list[PlainStatement], language: str) -> str:
    first_index = {s.sentence_id: i for i, s in enumerate(sentences)}
    heading_of = {s.sentence_id: s.heading for s in sentences}
    lines = ["Din journal på enkel svenska" if language == "sv" else "Your record in plain language", ""]
    current: str | None = "__start__"
    for st in sorted(statements, key=lambda x: first_index.get(x.source_sentence_ids[0], 0)):
        h = heading_of.get(st.source_sentence_ids[0])
        if h != current:
            if h:
                lines += ["", h] if len(lines) > 2 else [h]
            current = h
        lines.append(f"• {st.text}")
    return "\n".join(lines).strip() + "\n"


def explain_record(text: str, provider: LLMProvider, language: str = "en") -> RecordExplainResponse:
    sentences = split_record(text)
    warnings: list[str] = []
    out_lang = language if provider.name != "demo" else "en"
    if provider.name == "demo":
        warnings.append("Demo mode: a small glossary replaces medical terms; it is not a real plain-language rewrite.")
        if language == "sv":
            warnings.append("Swedish output needs the Claude provider; the demo engine wrote English.")

    by_id = {s.sentence_id: s for s in sentences}
    statements: list[PlainStatement] = []
    if sentences:
        output = provider.simplify_record(sentences, out_lang)
        for cand in output.statements:
            ids = [i for i in dict.fromkeys(cand.source_sentence_ids) if i in by_id]
            plain = (cand.text or "").strip()
            if not ids or not plain:
                warnings.append("A plain-language sentence was removed because it did not cite a valid original sentence.")
                continue
            source = " ".join(by_id[i].text for i in ids)
            checks = text_meaning_checks(source, plain, out_lang, "en")
            terms = [f"{term} → {simple}" for term, simple in simplify_text(source)[1]]
            statements.append(PlainStatement(statement_id=f"E{len(statements) + 1:03d}", source_sentence_ids=ids,
                                             text=plain, meaning_checks=checks, risk=risk_level(checks),  # type: ignore[arg-type]
                                             terms_explained=list(dict.fromkeys(terms))[:6]))
    covered = {i for st in statements for i in st.source_sentence_ids}
    unexplained = [s.sentence_id for s in sentences if s.sentence_id not in covered]
    if unexplained:
        warnings.append(f"{len(unexplained)} original sentence(s) have no plain-language version — content may be "
                        "missing. They are highlighted for review.")
    return RecordExplainResponse(
        created_at=datetime.now(timezone.utc), language=out_lang, provider=provider.name,  # type: ignore[arg-type]
        provider_label=provider.label, model=provider.model, sentences=sentences, statements=statements,
        unexplained_sentence_ids=unexplained, warnings=warnings,
        plain_text=build_record_plain_text(sentences, statements, out_lang))
