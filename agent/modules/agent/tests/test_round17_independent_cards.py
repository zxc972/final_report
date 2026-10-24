"""Independent-card evidence and blinding checks; all tests are offline."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.knowledge import prepare_condition_test_cards as p


def blank_card():
    return {"method_id": "test_method", "name": "test", **{k: [] for k in p.FIELDS}}


def test_exact_source_quote_and_offsets_are_checked():
    source = "Before. Required T1 input. After."
    card = blank_card()
    card["inputs"] = [
        {
            "statement": "A T1 input is needed",
            "quote": "Required T1 input.",
            "source_id": "s",
            "claim_type": "direct",
        }
    ]
    card, good, bad = p.validate_card(card, {"method_id": "test_method"}, {"s": source})
    assert len(good) == 1 and not bad
    span = good[0]["source_span"]
    assert source[span["start"] : span["end"]] == good[0]["quote"]
    assert not any(k.startswith("gold_") for k in good[0])


def test_unsupported_quote_or_source_is_quarantined_not_repaired():
    card = blank_card()
    card["conditions"] = [
        {
            "statement": "x",
            "quote": "Unsupported quote",
            "source_id": "s",
            "claim_type": "direct",
        },
        {
            "statement": "x",
            "quote": "Required T1 input.",
            "source_id": "other",
            "claim_type": "direct",
        },
    ]
    card, good, bad = p.validate_card(
        card, {"method_id": "test_method"}, {"s": "Required T1 input."}
    )
    assert not good and len(bad) == 2 and card["conditions"] == []


def test_fixed_test_methods_fields_and_document_split():
    gold = json.loads(
        (ROOT / "evaluation/condition_gold/gold_reviewed_v1.json").read_text()
    )
    old_methods = {i["method"] for i in gold["items"]}
    assert len(p.METHODS) == 4
    assert not old_methods & {m["method_id"] for m in p.METHODS}
    assert set(p.ANNOTATION_FIELDS) == {i["field"] for i in gold["items"]}
    active = {sid for m in p.METHODS for sid in m["sources"]}
    assert "afni_nmt_v2" not in active and "afni_charm" in active
    assert "-surface-vertex-areas" in p.SOURCES["wb_vertex_areas"]


def test_html_projection_removes_scripts_and_keeps_contiguous_evidence():
    parser = p.SourceText()
    parser.feed(
        "<nav>Ignore nav</nav><p>A <b>T1</b> input.</p><script>Ignore script</script><p>Next.</p>"
    )
    text = parser.text()
    assert "A T1 input." in text and "Next." in text
    assert "Ignore" not in text
