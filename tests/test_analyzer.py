from pathlib import Path

import pytest

from app.analyzer import analyze


def test_sample_counts_and_lines():
    text = (Path(__file__).parents[1] / "app/static/sample.log").read_text(encoding="utf-8")
    result = analyze(text)
    assert result["summary"] == {"line_count": 19, "error_count": 5, "warning_count": 0, "info_count": 0, "group_count": 4}
    group = result["groups"][0]
    assert group["count"] == 2
    assert [(o["start_line"], o["end_line"]) for o in group["occurrences"]] == [(3, 5), (7, 9)]
    assert group["related_mod_candidates"] == ["ExampleColony"]


def test_clean_log():
    assert analyze("Game initialized\nLoading complete\n")['summary']['error_count'] == 0


@pytest.mark.parametrize("message,rule", [
    ("NullReferenceException: x", "reference"),
    ("XML error: invalid definition", "xml"),
    ("Error: PatchOperationReplace failed", "xml"),
    ("TypeLoadException: missing type", "assembly"),
    ("Error: unrecognized problem", "unknown"),
])
def test_classification(message, rule):
    assert analyze(message)["groups"][0]["rule_id"] == rule


def test_different_messages_and_frames_are_not_merged():
    result = analyze("Error: item 1\n  at Example.A ()\nError: item 2\n  at Example.A ()\nError: item 1\n  at Example.B ()")
    assert result["summary"]["group_count"] == 3


def test_multiline_inner_exception_stays_in_event():
    result = analyze("Error: outer failure\n ---> System.TypeLoadException: missing\n  at Demo.Run ()\nDone")
    assert result["summary"]["error_count"] == 1
    assert result["groups"][0]["occurrences"][0]["end_line"] == 3


def test_timestamp_normalization():
    result = analyze("2026-11-02 12:00:01 Error: same\n2026-11-02 12:00:02 Error: same")
    assert result["summary"]["group_count"] == 1
    assert result["groups"][0]["count"] == 2


def test_raw_korean_and_markup_preserved():
    raw = 'Error: 한글 <img src=x onerror=alert(1)>'
    assert analyze(raw)["groups"][0]["occurrences"][0]["raw"] == raw


def test_mod_namespace_is_not_invented_as_mod_identity():
    result = analyze("NullReferenceException: test\n  at MyNamespace.Class.Method ()")
    assert result["groups"][0]["related_mod_candidates"] == []


def test_indented_error_is_new_event():
    assert analyze("Error: first\n  Error: second")["summary"]["error_count"] == 2


def test_loader_fallback_not_counted_as_error():
    r = analyze("Fallback handler could not load library C:/Game/MonoBleedingEdge/data-example.dll")
    assert r["summary"]["error_count"] == 0
    assert r["summary"]["info_count"] == 1


def test_unresolved_saved_reference_is_warning_not_failure():
    r = analyze("Could not resolve reference to object with loadID Thing_Test of type Verse.Pawn.")
    assert r["summary"]["error_count"] == 0
    assert r["summary"]["warning_count"] == 1


def test_loader_notice_does_not_hide_subsequent_real_exception():
    r = analyze("Fallback handler could not load library C:/Game/test.dll\nTypeLoadException: Could not load type Example.Widget")
    assert r["summary"]["error_count"] == 1
    assert r["summary"]["info_count"] == 1


def test_generic_failure_phrase_is_not_certain_error():
    r = analyze("Could not load optional asset")
    assert r["summary"]["error_count"] == 0
    assert r["summary"]["warning_count"] == 1
