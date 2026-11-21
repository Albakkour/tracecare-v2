from app.schemas.coverage import ChecklistAssessment
from app.services.checklist_service import load_registry
from app.services.coverage_calculator import calculate_coverage

TEMPLATE = load_registry()["headache_demo_v1"]


def report(statuses: list[str]):
    items = [ChecklistAssessment(item_id=item.item_id, label=item.label, status=status)
             for item, status in zip(TEMPLATE.items, statuses)]
    return calculate_coverage(TEMPLATE, items)


def test_blueprint_walkthrough_example():
    r = report(["asked_and_addressed", "asked_and_addressed", "asked_but_unanswered", "not_found_in_transcript",
                "not_found_in_transcript", "volunteered_not_asked", "not_found_in_transcript", "asked_and_addressed"])
    assert (r.question_coverage.numerator, r.question_coverage.denominator) == (4, 8)
    assert (r.information_capture.numerator, r.information_capture.denominator) == (4, 8)
    assert r.question_coverage.percentage == 50.0
    assert r.template_id == "headache_demo_v1" and r.template_version == "1.0-demo"
    assert r.is_provisional and r.review_status == "provisional"


def test_volunteered_counts_for_information_but_not_question():
    r = report(["volunteered_not_asked"] + ["not_found_in_transcript"] * 7)
    assert r.question_coverage.numerator == 0
    assert r.information_capture.numerator == 1


def test_asked_but_unanswered_counts_for_question_but_not_information():
    r = report(["asked_but_unanswered"] + ["not_found_in_transcript"] * 7)
    assert r.question_coverage.numerator == 1
    assert r.information_capture.numerator == 0


def test_not_applicable_is_excluded_from_both_denominators():
    r = report(["not_applicable", "asked_and_addressed"] + ["not_found_in_transcript"] * 6)
    assert r.question_coverage.denominator == 7 and r.information_capture.denominator == 7
    assert r.not_applicable_count == 1


def test_unclear_is_excluded_and_counted_as_pending():
    r = report(["unclear_needs_review", "unclear_needs_review", "asked_and_addressed"] + ["not_found_in_transcript"] * 5)
    assert r.question_coverage.denominator == 6
    assert r.pending_review_count == 2


def test_not_found_remains_in_denominator():
    r = report(["not_found_in_transcript"] * 8)
    assert r.question_coverage.denominator == 8
    assert r.question_coverage.percentage == 0.0
    assert r.not_found_count == 8


def test_zero_denominator_returns_unavailable():
    r = report(["not_applicable"] * 4 + ["unclear_needs_review"] * 4)
    assert r.coverage_available is False
    assert r.question_coverage.percentage is None and r.information_capture.percentage is None
    assert "not available" in r.message.lower()


def test_reviewed_when_all_items_reviewed():
    items = [ChecklistAssessment(item_id=i.item_id, label=i.label, status="asked_and_addressed", reviewed=True)
             for i in TEMPLATE.items]
    r = calculate_coverage(TEMPLATE, items)
    assert not r.is_provisional and r.review_status == "reviewed"
