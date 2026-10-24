"""Round 12 structured review, initial observations and path compatibility."""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products
from test_round8_closure import sealed

protocol = importlib.import_module(agent.__package__ + ".analysis_review_protocol")
internal = importlib.import_module(agent.__package__ + ".analysis_internal_review")
evidence = importlib.import_module(agent.__package__ + ".analysis_review_evidence")
data_card = importlib.import_module(agent.__package__ + ".analysis_data_card")
planner = importlib.import_module(agent.__package__ + ".analysis_product_planner")


def valid_review():
    return {
        "decision": "pass",
        "findings": [],
        "limitations": ["Synthetic engineering only"],
        "hard_block_disclosure": {
            "complete": True,
            "undisclosed_constraint_ids": [],
            "evidence_files": ["evidence_card"],
            "reason": "No observed hard blockers",
        },
    }


@pytest.mark.parametrize(
    "prefix,suffix,warnings",
    [
        ("", "", []),
        ("Explanation\n", " done", ["leading_text", "trailing_text"]),
        ("```json\n", "\n```", ["leading_text", "trailing_text"]),
    ],
)
def test_first_complete_review_object(prefix, suffix, warnings):
    review, actual = protocol.parse_structured_review(
        prefix + json.dumps(valid_review()) + suffix,
        {"evidence_card"},
        {"hard_blocks": []},
    )
    assert review["decision"] == "pass" and actual == warnings


@pytest.mark.parametrize(
    "content", ["unstructured approval", "{}", '{"decision":"pass"}']
)
def test_prose_and_incomplete_schema_never_approve(content):
    with pytest.raises(ValueError):
        protocol.parse_structured_review(
            content, {"evidence_card"}, {"hard_blocks": []}
        )


def test_format_failure_retries_once_and_charges_each_attempt(tmp_path, monkeypatch):
    tools, _, _ = sealed(tmp_path, monkeypatch)
    monkeypatch.setattr(
        internal,
        "collect_context",
        lambda *args: ({"files": {}, "registered_evidence_ids": []}, set()),
    )
    charged = []

    class Reviewer:
        calls = 0

        def invoke(self, messages):
            self.calls += 1
            assert "evidence_card" in json.loads(messages[1]["content"])
            if self.calls == 2:
                assert "No complete review JSON object" in messages[-1]["content"]
            return SimpleNamespace(
                content="pure prose" if self.calls == 1 else json.dumps(valid_review())
            )

    reviewer = Reviewer()
    result = internal.run_review(
        tools.workdir,
        "fixture",
        {},
        reviewer,
        lambda: charged.append(1),
        evidence_card={"hard_blocks": []},
    )
    assert result["decision"] == "pass" and result["protocol_attempts"] == 2
    assert reviewer.calls == len(charged) == 2


def test_historical_flash_prose_is_unreviewed_after_two_invalid_attempts(
    tmp_path, monkeypatch
):
    tools, _, _ = sealed(tmp_path, monkeypatch)
    monkeypatch.setattr(
        internal, "collect_context", lambda *args: ({"files": {}}, set())
    )
    path = Path(__file__).parent / "fixtures/round11_flash_invalid_review.json"
    fixture = json.loads(path.read_text())

    class Reviewer:
        calls = 0

        def invoke(self, messages):
            self.calls += 1
            return SimpleNamespace(content=fixture["raw_model_content"])

    reviewer = Reviewer()
    result = internal.run_review(
        tools.workdir,
        "fixture",
        {},
        reviewer,
        lambda: None,
        evidence_card={"hard_blocks": []},
    )
    assert result["decision"] == result["status"] == "unreviewed"
    assert result["protocol_valid"] is False and reviewer.calls == 2
    overall = importlib.import_module(agent.__package__ + ".analysis_overall_status")
    card = overall.finalize_card(
        {"verdict": "qualified"},
        {"internal_review": result},
        "incomplete_review",
        {"status": "success", "exit_code": 0},
        "finalized",
    )
    assert (
        card["verdict"] == "deferred"
        and card["component_statuses"]["execution"] == "passed"
    )


def test_all_candidate_hard_blocks_survive_large_previews(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    tools.plan_analysis({"measures": ["lgi"]})
    card = evidence.build_evidence_card(tools, {})
    ids = {row["local_constraint_id"] for row in card["hard_blocks"]}
    assert all(row["constraint_id"] == row["method_id"]+":"+row["local_constraint_id"] for row in card["hard_blocks"])
    assert {"software_available", "recon_complete"} <= ids
    assert any(
        row["command"] == "matlab" and row["available"] is False
        for row in card["software_observations"]
    )
    assert card["not_truncated"] is True
    review = valid_review()
    review["decision"] = "revise"
    review["hard_block_disclosure"].update(
        complete=False,
        undisclosed_constraint_ids=["recon_complete"],
        reason="Report mentions MATLAB only",
    )
    review["findings"] = [
        {
            "severity": "blocking",
            "claim": "Requested lGI prerequisites were not fully disclosed",
            "observation": "recon_complete is also blocked",
            "evidence_files": ["evidence_card"],
            "question": "Disclose the missing reconstruction history separately",
        }
    ]
    parsed, _ = protocol.parse_structured_review(
        json.dumps(review), {"evidence_card"}, card
    )
    assert parsed["decision"] == "revise"


def test_relative_code_path_normalizes_but_traversal_is_rejected(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    result = tools.plan_analysis({"measures": ["thickness"], "regions": "all regions"})
    candidate = result["candidates"][0]["candidate_id"]
    with pytest.raises(ValueError):
        planner.commit_candidate(
            tools, candidate, "Synthetic path check", "../analysis.py"
        )
    committed = planner.commit_candidate(
        tools, candidate, "Synthetic path check", "aparc.py"
    )
    assert committed["status"] == "committed"
    assert committed["plan"]["code_path"] == "/work/aparc.py"
    assert committed["path_normalization"]["original"] == "aparc.py"


def test_data_card_is_bounded_and_keeps_species_unverified(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    profile = tools.control_store.latest("data_profile")["record"]
    card = data_card.summarize(
        profile,
        [{"subject_id": "fixture", "index": 0, "species_declared": "human"}],
        {"inventory": {"commands": {"matlab": {"executable": False}}}},
    )
    assert len(card["summary"]) <= 1500
    assert card["subjects"][0]["species_verified"] is None
    assert "matlab=no" in card["summary"] and "verified=null" in card["summary"]
    assert "aparc" in card["summary"] and "thickness" in card["summary"]


def test_legacy_card_is_not_initialized(tmp_path, monkeypatch):
    from test_analysis_knowledge_profiles import make_tools

    tools = make_tools(tmp_path, monkeypatch, "legacy_v13")
    assert data_card.prepare_data_card(tools, "fixture") is None


def test_model_identity_is_from_response_ledger(tmp_path, monkeypatch):
    chat = importlib.import_module(agent.__package__ + ".agent_chat_state")
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = chat.ChatSession(
        workspace, "fixture-user", "fixture-conversation", "fixture-secret", 30
    )
    charged = session.budget.reserve("analysis")
    session.budget.finish(
        charged,
        {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "response_received",
        model="actual-provider-model",
    )
    view = session.budget.view()
    assert view["models"] == ["actual-provider-model"]
    assert view["model_source"] == "provider_response"
    assert view["known_tokens"]["total_tokens"] == 3


def test_format_exhaustion_is_not_counted_as_transport_failure():
    policy = importlib.import_module(
        agent.__package__ + ".analysis_failure_classification"
    )
    metadata = {
        "route": "analysis",
        "status": "incomplete_review",
        "validation": {
            "internal_review": {
                "decision": "unreviewed",
                "protocol_attempts": 2,
                "protocol_valid": False,
                "transport_exhausted": False,
            }
        },
    }
    result = policy.classify(metadata)
    assert result["category"] == "review_incomplete"
    assert result["stop_eligible"] is True
    assert policy.should_stop([result, result])
