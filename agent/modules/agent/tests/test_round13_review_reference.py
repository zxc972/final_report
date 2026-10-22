"""Replay untouched round-12 drafts and immutable failed constraints."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products

protocol = importlib.import_module(agent.__package__ + ".analysis_review_protocol")
cross = importlib.import_module(agent.__package__ + ".analysis_crossspecies")
binding = importlib.import_module(agent.__package__ + ".analysis_constraint_binding")


def test_real_p1_2_draft_valid_only_when_profile_summary_is_supplied():
    fixture = json.loads((Path(__file__).parent / "fixtures/round12_p1_2_review_binding.json").read_text())
    with pytest.raises(ValueError, match="unavailable evidence"):
        protocol.parse_structured_review(fixture["raw_review"], set(fixture["registered_before"]), fixture["evidence_card"])
    parsed, _ = protocol.parse_structured_review(fixture["raw_review"], set(fixture["registered_after"]), fixture["evidence_card"])
    assert parsed["decision"] == "revise"  # Valid protocol does not waive the review's findings.


