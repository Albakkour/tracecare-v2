from app.services.transcript_parser import parse_transcript
from tests.conftest import SAMPLE_TRANSCRIPT


def test_segments_have_stable_sequential_ids_and_speakers():
    parsed = parse_transcript(SAMPLE_TRANSCRIPT)
    assert [s.segment_id for s in parsed.segments] == [f"S{i:03d}" for i in range(1, 9)]
    assert [s.speaker for s in parsed.segments[:2]] == ["clinician", "patient"]
    assert [s.turn_index for s in parsed.segments] == list(range(1, 9))
    # Re-parsing the same text yields identical IDs (stable).
    assert parse_transcript(SAMPLE_TRANSCRIPT).segments == parsed.segments


def test_original_text_and_offsets_are_preserved():
    parsed = parse_transcript(SAMPLE_TRANSCRIPT)
    seg = parsed.segments[1]
    assert seg.text == "I've had a headache for three days."
    for s in parsed.segments:
        assert parsed.normalized_text[s.start_char:s.end_char] == s.text


def test_aci_bench_bracket_format_and_guest_speaker():
    parsed = parse_transcript("[doctor] how are you ?\n[patient] i'm okay .\n[patient_guest] he is not okay .")
    assert [s.speaker for s in parsed.segments] == ["clinician", "patient", "other"]
    assert parsed.segments[0].text == "how are you ?"
    assert parsed.segments[2].speaker_label == "patient_guest"


def test_crlf_line_endings_are_normalized():
    parsed = parse_transcript("Doctor: Hi.\r\nPatient: Hello.\r\n")
    assert len(parsed.segments) == 2
    assert parsed.normalized_text[parsed.segments[1].start_char:parsed.segments[1].end_char] == "Hello."


def test_unlabelled_lines_are_not_inferred():
    parsed = parse_transcript("Doctor: Any fever?\nNo fever at all.\nPatient: Okay.")
    assert parsed.segments[1].speaker == "unknown"
    assert parsed.segments[1].speaker_label is None
    assert any("not inferred" in w for w in parsed.warnings)
