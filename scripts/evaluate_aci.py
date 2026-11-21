"""Prototype engineering evaluation of the TraceCare pipeline on ACI-Bench (role-played encounters).

    cd backend
    .venv/bin/python -I ../scripts/evaluate_aci.py ../data/aci-bench-corpus                  # demo provider (free)
    .venv/bin/python -I ../scripts/evaluate_aci.py ../data/aci-bench-corpus --provider anthropic --limit 5

Runs the full pipeline on (a) the human transcripts and (b) the automatic speech-recognition (ASR) transcripts
of the ACI subset, and reports traceability (do generated statements resolve to source-linked facts?),
validation outcomes, checklist-template coverage, and a reference-note agreement proxy (how many extracted
patient symptoms are also mentioned in the dataset's human-written note). Writes
backend/app/evaluation/aci.json for the app's Evaluation page. Engineering checks, not clinical validation.
The anthropic provider spends API credit: use --limit.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.llm.factory import get_provider  # noqa: E402
from app.schemas.facts import CLINICIAN_CATEGORIES  # noqa: E402
from app.services.checklist_service import get_templates  # noqa: E402
from app.services.pipeline import run_analysis  # noqa: E402

csv.field_size_limit(10**9)
CITATION = ("Yim W, et al. ACI-BENCH: a Novel Ambient Clinical Intelligence Dataset for Benchmarking Automatic Visit "
            "Note Generation. Scientific Data, 2023. https://github.com/wyim/aci-bench")
HUMAN = ["challenge_data/train.csv", "challenge_data/valid.csv", "challenge_data/clinicalnlp_taskB_test1.csv",
         "challenge_data/clinicalnlp_taskC_test2.csv", "challenge_data/clef_taskC_test3.csv"]
ASR = ["src_experiment_data/train_aci_asr.csv", "src_experiment_data/valid_aci_asr.csv",
       "src_experiment_data/test1_aci_asr.csv", "src_experiment_data/test2_aci_asr.csv",
       "src_experiment_data/test3_aci_asr.csv"]


def load(aci_dir: Path, files: list[str]) -> list[dict]:
    rows = []
    for rel in files:
        path = aci_dir / rel
        if path.exists():
            rows += list(csv.DictReader(open(path, encoding="utf-8")))
    return rows


def mentioned_in_note(concept: str, note: str) -> bool:
    words = [w for w in re.findall(r"[a-z]+", concept.lower()) if len(w) >= 4 and w not in {"pain", "symptoms"}]
    words = words or [w for w in re.findall(r"[a-z]+", concept.lower()) if len(w) >= 4]
    return any(w[:5] in note.lower() for w in words)


def evaluate(rows: list[dict], provider, templates) -> dict:
    status = Counter()
    findings = Counter()
    template_use = Counter()
    statements = resolved = flagged = with_coverage = unexplored = clinician_facts = 0
    symptom_total = symptom_in_note = 0
    q_pcts: list[float] = []
    i_pcts: list[float] = []
    for n, row in enumerate(rows, start=1):
        r = run_analysis(row["dialogue"], templates, provider)
        known = {f.fact_id for f in r.facts}
        status.update(f.evidence_status for f in r.facts)
        status["rejected"] += len(r.rejected_facts)
        findings.update(f.code for f in r.validation_findings)
        clinician_facts += sum(f.category in CLINICIAN_CATEGORIES for f in r.facts)
        for s in [s for sec in r.clinical_note.sections for s in sec.statements if s.kind == "fact"] + \
                r.patient_explanation.statements:
            statements += 1
            resolved += bool(s.fact_ids) and set(s.fact_ids) <= known
        flagged += sum(bool(s.meaning_checks) for s in r.patient_explanation.statements)
        unexplored += sum(1 for s in r.symptoms if s.followed_up is False)
        reports = [c for c in r.coverage_reports if c.coverage_available and c.template_id]
        if reports:
            with_coverage += 1
            template_use.update(c.template_id for c in reports)
            q_pcts.append(reports[0].question_coverage.percentage or 0.0)
            i_pcts.append(reports[0].information_capture.percentage or 0.0)
        note = row.get("note", "")
        for f in r.facts:
            if f.category == "symptom" and f.polarity == "positive" and f.evidence_status == "source_linked":
                symptom_total += 1
                symptom_in_note += mentioned_in_note(f.concept, note)
        if n % 50 == 0:
            print(f"  {n}/{len(rows)}", file=sys.stderr)

    total_facts = sum(status.values())
    pct = lambda a, b: round(100 * a / b, 1) if b else None  # noqa: E731
    return {
        "encounters": len(rows),
        "facts_proposed": total_facts,
        "facts_per_encounter": round(total_facts / max(len(rows), 1), 1),
        "clinician_statements_per_encounter": round(clinician_facts / max(len(rows), 1), 1),
        "fact_status_pct": {k: pct(v, total_facts) for k, v in status.items()},
        "statements_generated": statements,
        "statements_resolving_pct": pct(resolved, statements),
        "patient_sentences_flagged_meaning": flagged,
        "encounters_with_coverage_pct": pct(with_coverage, len(rows)),
        "templates_used": dict(template_use.most_common()),
        "median_question_coverage_pct": round(statistics.median(q_pcts), 1) if q_pcts else None,
        "median_information_capture_pct": round(statistics.median(i_pcts), 1) if i_pcts else None,
        "unexplored_symptoms_per_encounter": round(unexplored / max(len(rows), 1), 2),
        "symptoms_also_in_reference_note_pct": pct(symptom_in_note, symptom_total),
        "validation_findings": dict(findings.most_common()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("aci_dir", type=Path)
    ap.add_argument("--provider", default="demo", choices=["demo", "anthropic"])
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    provider = get_provider(args.provider, get_settings())
    templates = get_templates([])
    human, asr = load(args.aci_dir, HUMAN), load(args.aci_dir, ASR)
    if args.limit:
        human, asr = human[: args.limit], asr[: args.limit]
    result = {
        "dataset": "ACI-Bench", "citation": CITATION, "generated": date.today().isoformat(),
        "provider": provider.label,
        "human_transcripts": evaluate(human, provider, templates),
        "asr_transcripts": evaluate(asr, provider, templates) if asr else None,
        "notes": [
            "Reference-note agreement is a proxy: share of extracted patient symptoms whose name also appears in the "
            "dataset's human-written note.",
            "ASR transcripts contain recognition errors; the comparison shows how traceability holds up.",
            "Engineering metrics on role-played data; not a measure of clinical accuracy.",
        ],
    }
    out = Path(__file__).resolve().parent.parent / "backend" / "app" / "evaluation" / "aci.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
