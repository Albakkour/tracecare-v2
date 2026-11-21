"""Consultation coverage metrics. Calculated in Python, never by the LLM.

N = applicable, assessable items = all items except `unclear_needs_review` and `not_applicable`.
Clinician question coverage = (asked_and_addressed + asked_but_unanswered) / N
Information capture coverage = (asked_and_addressed + volunteered_not_asked) / N
Equal item weights. No combined score is computed.
"""

from __future__ import annotations

from collections import Counter

from app.schemas.coverage import ITEM_STATUSES, ChecklistAssessment, ChecklistTemplate, CoverageMetric, CoverageReport

QUESTION_STATUSES = {"asked_and_addressed", "asked_but_unanswered"}
INFORMATION_STATUSES = {"asked_and_addressed", "volunteered_not_asked"}
EXCLUDED_STATUSES = {"unclear_needs_review", "not_applicable"}

COVERAGE_NOT_AVAILABLE = "Coverage not available: no applicable, assessable checklist items."


def _metric(label: str, numerator: int, denominator: int) -> CoverageMetric:
    if denominator == 0:
        return CoverageMetric(label=label, numerator=0, denominator=0, percentage=None, available=False,
                              message=COVERAGE_NOT_AVAILABLE)
    return CoverageMetric(label=label, numerator=numerator, denominator=denominator,
                          percentage=round(numerator / denominator * 100, 1), available=True)


def calculate_coverage(template: ChecklistTemplate, items: list[ChecklistAssessment]) -> CoverageReport:
    counts = Counter(i.status for i in items)
    assessable = [i for i in items if i.status not in EXCLUDED_STATUSES]
    n = len(assessable)
    asked = sum(1 for i in assessable if i.status in QUESTION_STATUSES)
    captured = sum(1 for i in assessable if i.status in INFORMATION_STATUSES)

    is_provisional = any(not i.reviewed for i in items)
    return CoverageReport(
        coverage_available=n > 0,
        message=None if n > 0 else COVERAGE_NOT_AVAILABLE,
        template_id=template.template_id,
        template_version=template.version,
        template_name=template.display_name,
        template_status=template.status,
        question_coverage=_metric("Clinician question coverage", asked, n),
        information_capture=_metric("Information capture coverage", captured, n),
        assessable_count=n,
        pending_review_count=counts.get("unclear_needs_review", 0),
        not_applicable_count=counts.get("not_applicable", 0),
        not_found_count=counts.get("not_found_in_transcript", 0),
        status_counts={s: counts.get(s, 0) for s in ITEM_STATUSES},
        is_provisional=is_provisional,
        review_status="provisional" if is_provisional else "reviewed",
        items=items,
    )


def no_template_report(message: str) -> CoverageReport:
    return CoverageReport(coverage_available=False, message=message, is_provisional=True)
