"""Calibrate TraceCare's meaning-change checks on PLABA (human plain-language adaptations, sentence-aligned).

    cd backend && .venv/bin/python -I ../scripts/evaluate_plaba.py ../data/rnpmf-osfstorage-archive

Two measurements:
1. Review-flag rate on HUMAN adaptations. Human rewrites are meant to preserve meaning, so this approximates
   how often the checks ask a reviewer to look at a sentence that is actually fine (an upper bound on false
   alarms; humans sometimes do drop numbers deliberately).
2. Detection rate on deliberately corrupted adaptations: we remove a negation, change a number, or remove a
   hedge from a human adaptation and test whether the check flags it.

Writes backend/app/evaluation/plaba.json (shown in the app's Evaluation page).
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.meaning import has_negation, has_uncertainty, numbers_in, text_meaning_checks  # noqa: E402

CITATION = ("Attal K, Ondov B, Demner-Fushman D. A dataset for plain language adaptation of biomedical abstracts. "
            "Scientific Data, 2023. https://osf.io/rnpmf/")
NEG_WORDS = re.compile(r"\b(not|no|never|without|none)\s+|n't\b", re.I)
HEDGE_WORDS = re.compile(r"\b(may|might|could|possibly|probably|likely|perhaps|suggests?)\s+", re.I)
NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w])")


def pairs(data: dict):
    for qid, q in data.items():
        for pmid, rec in q.items():
            if not isinstance(rec, dict) or "abstract" not in rec:
                continue
            for adaptation in rec.get("adaptations", {}).values():
                for sid, src in rec["abstract"].items():
                    tgt = adaptation.get(sid)
                    if src and tgt and tgt.strip():
                        yield qid, pmid, src.strip(), tgt.strip()


def main() -> None:
    plaba_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../data/rnpmf-osfstorage-archive")
    data = json.loads((plaba_dir / "data.json").read_text(encoding="utf-8"))
    rng = random.Random(42)

    total = 0
    flagged = Counter()
    any_flag = 0
    examples = []
    neg_trials = neg_hits = num_trials = num_hits = hedge_trials = hedge_hits = 0

    for _, pmid, src, tgt in pairs(data):
        total += 1
        checks = text_meaning_checks(src, tgt)
        kinds = {c.check for c in checks}
        flagged.update(kinds)
        if kinds:
            any_flag += 1
            if len(examples) < 6 and rng.random() < 0.02:
                examples.append({"pmid": pmid, "original": src, "plain": tgt, "flags": [c.message for c in checks]})
        if kinds:
            continue  # corruption tests only on pairs the checker accepts as-is
        if has_negation(src) and has_negation(tgt) and NEG_WORDS.search(tgt):
            corrupted = NEG_WORDS.sub("", tgt, count=0)
            if not has_negation(corrupted):
                neg_trials += 1
                neg_hits += any(c.check == "negation" for c in text_meaning_checks(src, corrupted))
        m = NUM.search(tgt)
        if m and float(m.group(1)) in numbers_in(src):
            corrupted = tgt[:m.start()] + str(int(float(m.group(1))) + 3) + tgt[m.end():]
            num_trials += 1
            num_hits += any(c.check == "number" for c in text_meaning_checks(src, corrupted))
        if has_uncertainty(src) and HEDGE_WORDS.search(tgt):
            corrupted = HEDGE_WORDS.sub("", tgt)
            if not has_uncertainty(corrupted):
                hedge_trials += 1
                hedge_hits += any(c.check == "uncertainty" for c in text_meaning_checks(src, corrupted))

    def rate(a: int, b: int) -> float | None:
        return round(100 * a / b, 1) if b else None

    result = {
        "dataset": "PLABA", "citation": CITATION, "generated": date.today().isoformat(),
        "sentence_pairs": total,
        "human_adaptations": {
            "flag_rate_any": rate(any_flag, total),
            "flag_rate_by_check": {k: rate(v, total) for k, v in flagged.items()},
            "interpretation": "Share of human plain-language sentences the checks send for review "
                              "(upper bound on false alarms).",
        },
        "corruption_detection": {
            "negation_removed": {"trials": neg_trials, "detected_pct": rate(neg_hits, neg_trials)},
            "number_changed": {"trials": num_trials, "detected_pct": rate(num_hits, num_trials)},
            "hedge_removed": {"trials": hedge_trials, "detected_pct": rate(hedge_hits, hedge_trials)},
        },
        "examples_flagged_human": examples,
    }
    out = Path(__file__).resolve().parent.parent / "backend" / "app" / "evaluation" / "plaba.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "examples_flagged_human"}, indent=2))


if __name__ == "__main__":
    main()
