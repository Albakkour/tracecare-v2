"""Deterministic meaning-preservation checks for plain-language rewrites (English and Swedish).

They flag a rewritten sentence that may have lost or added a negation, lost an uncertainty/hedge, or lost or
changed a number. They are heuristics: a flag means "please compare with the source", not "this is wrong".
Their false-alarm and detection rates are measured on the PLABA dataset (scripts/evaluate_plaba.py).
"""

from __future__ import annotations

import re

from app.schemas.facts import MedicalFact
from app.schemas.outputs import MeaningCheck

I = re.IGNORECASE

NEGATION = {
    "en": re.compile(r"\b(no|not|never|none|nothing|without|denied|denies|deny|neither|nor|negative for|absent)\b"
                     r"|n['’]t\b", I),
    "sv": re.compile(r"\b(inte|ingen|inget|inga|aldrig|utan|ej|varken|förnekar|negativ för)\b", I),
}
UNCERTAINTY = {
    "en": re.compile(r"\b(not sure|unsure|unclear|uncertain|unknown|not known|not clear|not certain|maybe|might|may|"
                     r"could|possibl[ey]|probabl[ey]|likely|unlikely|perhaps|suspected|suspect|query|consider|"
                     r"cannot be (?:excluded|ruled out)|rule out|(?:do|does|did)\s*n['’]?t (?:remember|know)|"
                     r"(?:can|could)\s*n['’]?t (?:remember|recall)|not (?:remember|recall)|forgot|forget|"
                     r"not established|don['’]t know|appears?|seems?|i think|i believe|i suspect|impression|"
                     r"looks like|sounds like|suspicious|concerning for|consistent with)\b", I),
    "sv": re.compile(r"\b(osäker|osäkert|oklart|okänt|kanske|möjligen|möjlig|möjligt|troligen|trolig|troligt|"
                     r"misstänkt|misstänks|eventuellt|kan vara|skulle kunna|verkar|minns inte|kommer inte ihåg|"
                     r"vet inte|inte fastställt|inte säker)\b", I),
}
NUMBER_WORDS = {
    "en": {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
           "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "once": 1, "twice": 2,
           "hundred": 100},
    "sv": {"två": 2, "tre": 3, "fyra": 4, "fem": 5, "sex": 6, "sju": 7, "åtta": 8, "nio": 9, "tio": 10,
           "elva": 11, "tolv": 12, "femton": 15, "tjugo": 20, "trettio": 30, "hundra": 100},
}
_PHRASE_ONE = {"en": re.compile(r"\b(a|one) (day|week|month|year|time)\b", I),
               "sv": re.compile(r"\b(en|ett) (gång|dag|vecka|månad|år)\b", I)}


# Words that already express absence or reduction: a rewrite using "not" for them adds no new negation.
REDUCTION = re.compile(r"\b(reduc\w*|decreas\w*|less|lower\w*|loss of|lack of|lacks?|absent|without|minimal|"
                       r"diminish\w*|poor|un\w+|in(?:ability|able)|minskad\w*|nedsatt\w*|sämre)\b", I)


def _lang(lang: str) -> str:
    return "sv" if lang == "sv" else "en"


def has_negation(text: str, lang: str = "en") -> bool:
    return bool(NEGATION[_lang(lang)].search(text or ""))


def has_uncertainty(text: str, lang: str = "en") -> bool:
    return bool(UNCERTAINTY[_lang(lang)].search(text or ""))


def numbers_in(text: str, lang: str = "en") -> set[float]:
    words = NUMBER_WORDS[_lang(lang)]
    pattern = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?|" + "|".join(words) + r")(?![\w])", I)
    found: set[float] = set()
    for m in pattern.finditer(text or ""):
        tok = m.group(1).lower()
        if tok in words:
            found.add(float(words[tok]))
        else:  # English "3,000" = 3000; Swedish "37,8" = 37.8
            found.add(float(tok.replace(",", "") if _lang(lang) == "en" else tok.replace(",", ".")))
    if _PHRASE_ONE[_lang(lang)].search(text or ""):
        found.add(1.0)
    return found


def fact_meaning_checks(text: str, facts: list[MedicalFact], lang: str = "en") -> list[MeaningCheck]:
    """Compare a rewritten sentence with the structured facts it cites."""
    checks: list[MeaningCheck] = []
    neg, unc = has_negation(text, lang), has_uncertainty(text, lang)
    source_wording = " ".join(f"{f.normalized_value} {f.supporting_quote}" for f in facts)
    if any(f.polarity == "negative" for f in facts) and not neg:
        checks.append(MeaningCheck(check="negation", message="The source fact is a denial, but the sentence has no negation."))
    # Only flag an added negation if the source wording has none (e.g. "not very hungry" is a positive
    # finding that is legitimately phrased with a negation).
    if facts and all(f.polarity == "positive" for f in facts) and neg and not unc and not has_negation(source_wording) \
            and not REDUCTION.search(source_wording):
        checks.append(MeaningCheck(check="negation", message="The sentence adds a negation that is not in the source."))
    if any(f.polarity == "uncertain" for f in facts) and not unc and not neg:
        checks.append(MeaningCheck(check="uncertainty", message="The source is uncertain, but the sentence does not say so."))
    source_numbers: set[float] = set()
    for f in facts:
        for value in (f.duration, f.frequency, f.severity):
            source_numbers |= numbers_in(value or "")
    missing = source_numbers - numbers_in(text, lang)
    if missing:
        checks.append(MeaningCheck(check="number", message="A number from the source is missing or changed: "
                                   + ", ".join(f"{n:g}" for n in sorted(missing))))
    return checks


def text_meaning_checks(source: str, rewritten: str, lang: str = "en", source_lang: str = "en") -> list[MeaningCheck]:
    """Compare a plain-language rewrite with the original sentence(s) (record explainer, PLABA evaluation)."""
    checks: list[MeaningCheck] = []
    s_neg, r_neg = has_negation(source, source_lang), has_negation(rewritten, lang)
    if s_neg and not r_neg:
        checks.append(MeaningCheck(check="negation", message="The original contains a negation that the plain version lacks."))
    elif r_neg and not s_neg and not has_uncertainty(rewritten, lang) and not REDUCTION.search(source):
        checks.append(MeaningCheck(check="negation", message="The plain version adds a negation that is not in the original."))
    if has_uncertainty(source, source_lang) and not has_uncertainty(rewritten, lang) and not r_neg:
        checks.append(MeaningCheck(check="uncertainty", message="The original is hedged or uncertain; the plain version sounds definite."))
    missing = numbers_in(source, source_lang) - numbers_in(rewritten, lang)
    if missing:
        checks.append(MeaningCheck(check="number", message="Number(s) from the original are missing or changed: "
                                   + ", ".join(f"{n:g}" for n in sorted(missing))))
    return checks


def risk_level(checks: list[MeaningCheck]) -> str:
    kinds = {c.check for c in checks}
    if kinds & {"negation", "number"}:
        return "high"
    if kinds:
        return "medium"
    return "low"
