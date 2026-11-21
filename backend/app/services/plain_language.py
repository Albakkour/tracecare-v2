"""A small clinical-term → everyday-English glossary for the deterministic demo engine.

The Claude provider does real plain-language rewriting; this glossary only lets the demo show the mechanics
(source-linked rewrites + meaning checks) without an API key.
"""

from __future__ import annotations

import re

GLOSSARY: dict[str, str] = {
    # findings / symptoms
    "tenderness to palpation": "pain when pressed", "tender to palpation": "painful when pressed",
    "tenderness": "soreness when pressed", "erythema": "redness", "edema": "swelling", "oedema": "swelling",
    "effusion": "fluid build-up", "dyspnea": "shortness of breath", "dyspnoea": "shortness of breath",
    "cephalalgia": "headache", "photophobia": "sensitivity to light", "phonophobia": "sensitivity to sound",
    "emesis": "vomiting", "pyrexia": "fever", "afebrile": "without fever", "febrile": "with a fever",
    "paresthesia": "pins and needles", "paraesthesia": "pins and needles", "tinnitus": "ringing in the ears",
    "pruritus": "itching", "syncope": "fainting", "malaise": "feeling generally unwell", "myalgia": "muscle pain",
    "arthralgia": "joint pain", "dysuria": "pain when passing urine", "hematuria": "blood in the urine",
    "haematuria": "blood in the urine", "tachycardia": "a fast heartbeat", "bradycardia": "a slow heartbeat",
    "hypertension": "high blood pressure", "hypotension": "low blood pressure", "papilledema": "swelling at the back of the eye",
    "lumbar": "lower back", "cervical spine": "neck", "anterior": "front", "posterior": "back", "bilateral": "on both sides",
    "unilateral": "on one side", "distal": "further from the body", "proximal": "closer to the body",
    "range of motion": "how far it can move", "gait": "way of walking", "acute": "recent and sudden",
    "chronic": "long-lasting", "benign": "not harmful", "idiopathic": "of unknown cause", "etiology": "cause",
    "aetiology": "cause", "prognosis": "expected outcome", "denies": "says they do not have",
    "reports": "says they have", "presents with": "came in with", "history of": "has had",
    "unremarkable": "normal", "within normal limits": "normal", "no acute distress": "not in distress",
    # treatment / plan
    "analgesic": "painkiller", "analgesia": "pain relief", "nsaid": "anti-inflammatory painkiller",
    "nsaids": "anti-inflammatory painkillers", "antipyretic": "fever-reducing medicine",
    "physiotherapy": "physiotherapy (exercise-based treatment)", "imaging": "scans or X-rays",
    "follow-up": "check-up", "referral": "being sent to a specialist", "prn": "as needed", "bid": "twice a day",
    "tid": "three times a day", "qd": "once a day", "po": "by mouth", "conservative management": "treatment without surgery",
}
_PATTERN = re.compile(r"\b(" + "|".join(sorted(map(re.escape, GLOSSARY), key=len, reverse=True)) + r")\b", re.IGNORECASE)


def simplify_text(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Replace known clinical terms. Returns (new text, [(term, plain), ...])."""
    used: list[tuple[str, str]] = []

    def sub(m: re.Match[str]) -> str:
        term = m.group(0)
        plain = GLOSSARY[term.lower()]
        used.append((term, plain))
        return plain

    return _PATTERN.sub(sub, text), used
