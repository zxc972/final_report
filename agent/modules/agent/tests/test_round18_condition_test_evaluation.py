"""Transport repair, immutable blind gold, and statement-level statistics."""
import hashlib
import json
from pathlib import Path
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.knowledge import provider_llm as transport
from tools.knowledge import run_condition_test_evaluation as run
from tools.knowledge import condition_evaluation_statistics as stats

c = run.base.load_canon()


class FakeProvider:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.called = []
        self.info = {}

    def complete(self, prompt):
        scope = transport._SCOPE.get()
        self.called.append((dict(scope), prompt))
        value = next(self.answers)
        self.info[scope["logical_id"]] = {"status": "http_error" if value is None else "ok",
                                       "finish_reason": "length" if value == "TRUNCATED" else "stop"}
        if value is None:
            raise transport.ProviderFailure("Provider request failed (http_error, HTTP 429)")
        return value

    def response_info(self, arm, item_id, sample):
        return self.info.get(f"{arm}:{item_id}:{sample}", {})


def test_interface_supplement_is_bounded_and_remaining_positions_continue():
    provider = FakeProvider([None, "ok", None, "ok", "ok", "ok"])
    caller = run.ResilientSamples(provider, "full_v2", 1001)
    assert [caller("prompt") for _ in range(5)] == ["ok", "", "ok", "ok", "ok"]
    assert caller.nominal == 5 and caller.interface_replacements == 1
    assert caller.missing == [2] and len(caller.failures) == 2
    assert len(provider.called) == 6


def test_length_and_interface_supplements_never_change_vote_positions():
    provider = FakeProvider(["TRUNCATED", None, "ok", "TRUNCATED", "ok", "ok", "ok"])
    caller = run.ResilientSamples(provider, "full_v2", 1001)
    assert [caller("prompt") for _ in range(5)] == ["ok", "TRUNCATED", "ok", "ok", "ok"]
    assert caller.interface_replacements == caller.length_replacements == 1
    assert caller.nominal == 5 and len(provider.called) == 7 and caller.missing == []


def test_development_repair_reuses_even_empty_and_invalid_received_answers(tmp_path):
    prompt = "same frozen prompt"
    events = []
    for sample, text in [(1, ""), (3, "not-json"), (5, '{"template":"advisory"}')]:
        request_id = str(sample)
        events += [{"event": "start", "request_id": request_id, "logical_id": f"full_v2:1:{sample}",
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()},
                   {"event": "end", "request_id": request_id, "logical_id": f"full_v2:1:{sample}",
                    "status": "ok", "text": text, "finish_reason": "stop"}]
    path = tmp_path / "old.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events))
    history = run.HistoricalAnswers(path)
    provider = FakeProvider(["new2", "new4"])
    caller = run.ResilientSamples(provider, "dev_full_v2_repair", 1, history)
    assert [caller(prompt) for _ in range(5)] == ["", "new2", "not-json", "new4", '{"template":"advisory"}']
    assert len(provider.called) == 2 and sum(r["historical"] for r in caller.records) == 3
    with pytest.raises(AssertionError):
        history.get("full_v2", 1, 1, "changed prompt")


def test_frozen_gold_is_the_blind_packet_and_wrong_digest_stops(tmp_path):
    assert len(run.verify_gold()["items"]) == 45
    folder = tmp_path / "evaluation/condition_gold"
    folder.mkdir(parents=True)
    (folder / "gold_test_v1.json").write_text("{}")
    with pytest.raises(AssertionError, match="Frozen gold changed"):
        run.verify_gold(tmp_path)


def test_exact_mcnemar_matches_closed_form_and_zero_discordance():
    m = stats.exact_mcnemar([True] * 10, [False] * 10)
    assert m["p_exact_two_sided"] == 2 / 1024
    assert m["first_only_correct"] == 10 and m["second_only_correct"] == 0
    assert stats.exact_mcnemar([True, False], [True, False])["p_exact_two_sided"] == 1
    assert stats.exact_mcnemar([True, False], [False, True])["p_exact_two_sided"] == 1


def test_bootstrap_keeps_set_scorer_zero_convention_and_pairs_draws():
    items = [{"id": i, "method": "m", "gold_template": "software", "gold_parameters": {"commands": ["matlab"]}} for i in [1, 2]]
    preds = [{"id": i, "decision": "accepted", "template": "software", "parameters": {"commands": ["matlab"]}} for i in [1, 2]]
    expected = run.base.score_with_details(c, items, preds)
    assert expected["key"]["tp"] == 1  # duplicate statements have one method/key
    a = stats.bootstrap(c, items, {"a": preds, "b": preds}, replicates=2000)
    b = stats.bootstrap(c, items, {"a": preds, "b": preds}, replicates=2000)
    assert a == b and a["arms"]["a"] == a["arms"]["b"]
    assert a["arms"]["a"]["metrics"] == expected
    assert a["arms"]["a"]["intervals_95"]["key.f1"] == {"estimate": 1, "low": 1, "high": 1}
    assert a["arms"]["a"]["intervals_95"]["advisory_or_not_executable.f1"]["high"] == 0


def test_statement_key_correctness_uses_existing_none_convention():
    item = {"gold_template": "advisory", "gold_parameters": None}
    assert stats.statement_key_correct(c, item, {"decision": "review", "template": "software", "parameters": {"commands": ["matlab"]}})
    item = {"gold_template": "software", "gold_parameters": {"commands": ["matlab"]}}
    assert not stats.statement_key_correct(c, item, {"decision": "review", "template": "software", "parameters": {"commands": ["matlab"]}})


def test_shared_budget_survives_resume_and_counts_http_failures(tmp_path):
    def handle(request):
        return httpx.Response(429)
    config = transport.Config(base_url="https://gateway.invalid/v1", api_key="round18-test-secret",
                              max_attempts=1)
    provider = transport.Provider(config, tmp_path, max_requests=2,
                                  client=httpx.Client(transport=httpx.MockTransport(handle)), sleep=lambda _: None)
    for arm in ["full_v2", "dev_full_v2_repair"]:
        with transport.scope(arm, 1, 1), pytest.raises(transport.ProviderFailure):
            provider.complete("prompt")
    provider.close()
    resumed = transport.Provider(config, tmp_path, max_requests=2,
                                client=httpx.Client(transport=httpx.MockTransport(handle)), sleep=lambda _: None)
    with transport.scope("direct_v2", 1, 1), pytest.raises(transport.ProviderFailure, match="budget is exhausted"):
        resumed.complete("prompt")
    assert resumed.stats()["http_attempts"] == 2 and resumed.stats()["failed_requests"] == 2
    assert "round18-test-secret" not in resumed.ledger.read_text()
    resumed.close()
