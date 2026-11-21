"""Prototype engineering evaluation of the TraceCare pipeline over ACI-Bench encounters.

    cd backend
    .venv/bin/python -I ../scripts/evaluate_aci.py ../data/aci-bench-corpus                  # demo provider, all splits
    .venv/bin/python -I ../scripts/evaluate_aci.py ../data/aci-bench-corpus --provider anthropic --limit 5

Reports traceability metrics (do generated statements resolve to source-linked facts? how many proposed
facts were rejected or flagged?) and coverage availability. These are engineering checks on role-played
data, not clinical validation. The anthropic provider spends API credit: use --limit.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.llm.factory import get_provider  # noqa: E402
from app.services.checklist_service import get_templates  # noqa: E402
from app.services.pipeline import run_analysis  # noqa: E402

csv.field_size_limit(10**9)
SPLITS = ["train.csv", "valid.csv", "clinicalnlp_taskB_test1.csv", "clinicalnlp_taskC_test2.csv", "clef_taskC_test3.csv"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("aci_dir", type=Path)
    ap.add_argument("--provider", default="demo", choices=["demo", "anthropic"])
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = []
    for split in SPLITS:
        path = args.aci_dir / "challenge_data" / split
        if path.exists():
            rows += [(split, r) for r in csv.DictReader(open(path, encoding="utf-8"))]
    if args.limit:
        rows = rows[: args.limit]

    provider = get_provider(args.provider, get_settings())
    templates = get_templates([])
    fact_status: Counter[str] = Counter()
    findings: Counter[str] = Counter()
    statements = resolved = flagged = 0
    coverage_available = 0
    q_pcts: list[float] = []
    i_pcts: list[float] = []
    by_template: Counter[str] = Counter()

    for n, (split, row) in enumerate(rows, start=1):
        result = run_analysis(row["dialogue"], templates, provider)
        known = {f.fact_id for f in result.facts}
        linked = {f.fact_id for f in result.facts if f.evidence_status == "source_linked"}
        fact_status.update(f.evidence_status for f in result.facts)
        fact_status["rejected"] += len(result.rejected_facts)
        findings.update(f.code for f in result.validation_findings)
        note_stmts = [s for sec in result.clinical_note.sections for s in sec.statements if s.kind == "fact"]
        for s in note_stmts + result.patient_explanation.statements:
            statements += 1
            resolved += bool(s.fact_ids) and set(s.fact_ids) <= known
        flagged += sum(bool(s.meaning_checks) for s in result.patient_explanation.statements)
        assert all(set(s.fact_ids) <= linked for s in result.patient_explanation.statements)
        for report in result.coverage_reports:
            if report.coverage_available and report.template_id:
                coverage_available += 1
                by_template[report.template_id] += 1
                q_pcts.append(report.question_coverage.percentage or 0.0)
                i_pcts.append(report.information_capture.percentage or 0.0)
        if n % 25 == 0:
            print(f"  processed {n}/{len(rows)}", file=sys.stderr)

    total_facts = sum(fact_status.values())
    print(f"Provider: {provider.label}")
    print(f"Encounters analysed: {len(rows)}")
    print(f"Proposed facts: {total_facts}  " + "  ".join(f"{k}={v} ({v / max(total_facts, 1):.0%})"
                                                     for k, v in fact_status.most_common()))
    print(f"Generated statements: {statements}; resolving to known fact IDs: {resolved} "
          f"({resolved / max(statements, 1):.1%})")
    print(f"Patient statements flagged for possible meaning change: {flagged}")
    print(f"Coverage reports computed: {coverage_available} {dict(by_template)}")
    if q_pcts:
        print(f"Median clinician question coverage: {statistics.median(q_pcts):.1f}%  "
              f"median information capture: {statistics.median(i_pcts):.1f}%")
    print("Validation findings by code: " + ", ".join(f"{k}={v}" for k, v in findings.most_common()))
    print("\nNote: engineering metrics on role-played data; not a measure of clinical accuracy.")


if __name__ == "__main__":
    main()
