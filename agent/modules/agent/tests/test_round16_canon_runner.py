"""Round 16 evaluation transport, accounting, freeze and scoring boundaries."""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[4]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = load("_r16_test_provider", ROOT / "tools/knowledge/provider_llm.py")
r = load("_r16_test_runner", ROOT / "tools/knowledge/run_condition_canonicalization.py")
c = r.load_canon()
SECRET = "round16-secret-fixture-do-not-log"


def provider(tmp_path, statuses=(200,), cap=800):
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        status = statuses[min(len(sent) - 1, len(statuses) - 1)]
        if status != 200:
            return httpx.Response(status, json={"error": SECRET})
        return httpx.Response(
            200,
            json={
                "model": "observed-flash",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"template":"none"}'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 3,
                    "total_tokens": 14,
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    config = p.Config(base_url="https://gateway.invalid/v1", api_key=SECRET)
    return p.Provider(config, tmp_path, cap, client=client, sleep=lambda _: None), sent


def call(adapter, sample=1, item=1):
    with p.scope("full", item, sample):
        return adapter.complete("one condition")


def test_samples_are_independent_but_successful_resume_is_cached(tmp_path):
    adapter, sent = provider(tmp_path)
    first = call(adapter, 1)
    assert call(adapter, 2) == first
    assert call(adapter, 1) == first
    assert len(sent) == 2
    assert all(
        x["temperature"] == 0.7 and x["model"] == "deepseek-v4.1-flash" for x in sent
    )
    assert adapter.stats()["total_tokens"] == 28
    replay, replay_sent = provider(tmp_path)
    assert call(replay, 1) == first and replay_sent == []
    assert replay.stats()["logical_calls"] == 2
    assert SECRET not in adapter.ledger.read_text()


def test_budget_is_reserved_before_sending_and_counts_retries(tmp_path):
    adapter, sent = provider(tmp_path, (429, 200), cap=2)
    call(adapter)
    with pytest.raises(p.ProviderFailure, match="budget"):
        call(adapter, item=2)
    assert len(sent) == 2
    stats = adapter.stats()
    assert stats["logical_calls"] == 1 and stats["http_attempts"] == 2
    assert stats["unknown_usage_requests"] == 1 and stats["failed_requests"] == 1
    assert stats["total_tokens"] == 14
    assert SECRET not in adapter.ledger.read_text()


def test_auth_failure_is_not_retried_or_logged_raw(tmp_path):
    adapter, sent = provider(tmp_path, (401,))
    with pytest.raises(p.ProviderFailure) as caught:
        call(adapter)
    assert len(sent) == 1
    assert SECRET not in str(caught.value) and SECRET not in adapter.ledger.read_text()
    assert adapter.stats()["unknown_usage_requests"] == 1


def test_parallel_requests_cannot_exceed_shared_cap(tmp_path):
    adapter, sent = provider(tmp_path, cap=8)

    def task(index):
        try:
            call(adapter, item=index)
            return True
        except p.ProviderFailure:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(task, range(10)))
    assert sum(outcomes) == len(sent) == adapter.stats()["http_attempts"] == 8


def test_missing_usage_is_unknown_not_reported_zero():
    assert p.usage_counts(None) == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
    }
    assert (
        p.usage_counts({"prompt_tokens": False, "completion_tokens": -1})[
            "input_tokens"
        ]
        is None
    )


def test_explicit_development_config_wins_over_inherited_environment(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PLATFORM_API_KEY", "another-fixture")
    monkeypatch.setenv("PLATFORM_API_BASE_URL", "https://other.invalid/v1")
    path = tmp_path / "dev.env"
    path.write_text(
        f"PLATFORM_API_BASE_URL=https://gateway.invalid/v1\nPLATFORM_API_KEY={SECRET}\n"
    )
    cfg = p.load_config(path)
    assert cfg.base_url == "https://gateway.invalid/v1" and cfg.api_key == SECRET
    assert SECRET not in repr(cfg) and SECRET not in json.dumps(cfg.public())


def test_freeze_refuses_changed_input_and_accidental_overwrite(tmp_path):
    digest = r.freeze_or_verify(
        tmp_path, {"gold_sha256": "a", "parameters": {"TAU": 0.6}}, False
    )
    assert digest == r.freeze_or_verify(
        tmp_path, {"gold_sha256": "a", "parameters": {"TAU": 0.6}}, True
    )
    with pytest.raises(ValueError, match="Frozen"):
        r.freeze_or_verify(
            tmp_path, {"gold_sha256": "b", "parameters": {"TAU": 0.6}}, True
        )
    with pytest.raises(ValueError, match="already"):
        r.freeze_or_verify(tmp_path, {"gold_sha256": "a"}, False)


def test_four_arms_use_original_sample_counts_and_do_not_send_gold():
    item = {
        "id": 1,
        "method": "m",
        "statement": "MATLAB software must be installed",
        "quote": "MATLAB is required.",
        "source_id": "s",
        "gold_template": "MUST_NOT_BE_SEEN",
        "gold_parameters": {"secret_label": "MUST_NOT_BE_SEEN"},
    }
    prompts = []

    def fake(prompt):
        prompts.append(prompt)
        return '{"template":"software","parameters":{"commands":["matlab"]}}'

    for arm, count in [("full", 5), ("k1", 1), ("retrieval_only", 0), ("direct", 1)]:
        before = len(prompts)
        prediction = r.predict(c, item, item["quote"], {"T1": ["space"]}, arm, fake)
        assert len(prompts) - before == count
        assert prediction["template"] == "software"
    assert all("MUST_NOT_BE_SEEN" not in prompt for prompt in prompts)
    assert (c.TAU, c.DELTA, c.SAMPLES) == (0.6, 0.2, 5)


def test_scoring_deduplicates_keys_but_keeps_statement_template_metric():
    item = {
        "id": 1,
        "method": "m",
        "gold_template": "software",
        "gold_parameters": {"commands": ["matlab"]},
    }
    items = [
        item,
        dict(item, id=2),
        dict(item, id=3, gold_template="advisory", gold_parameters=None),
    ]
    preds = [
        {
            "decision": "accepted",
            "template": "software",
            "parameters": {"commands": ["matlab"]},
        },
        {
            "decision": "review",
            "template": "software",
            "parameters": {"commands": ["matlab"]},
        },
        {"decision": "advisory", "template": "advisory", "parameters": None},
    ]
    metrics = r.score_with_details(c, items, preds)
    assert metrics["template_accuracy"] == 1
    assert metrics["executable"]["recall"] == 0.5
    assert metrics["key"]["f1"] == 1
    assert metrics["review_queue"] == 1
    assert metrics["advisory_or_not_executable"]["precision"] == 0.5


def test_full_error_list_includes_withheld_correct_template_and_wrong_parameters():
    item = {
        "id": 1,
        "method": "m",
        "field": "conditions",
        "statement": "Requires MATLAB",
        "quote": "MATLAB",
        "source_id": "s",
        "gold_template": "software",
        "gold_parameters": {"commands": ["matlab"]},
    }
    pred = {
        "decision": "review",
        "template": "software",
        "parameters": {"commands": ["matlab"]},
        "score": 0.5,
        "margin": 0.1,
        "support": 0.6,
    }
    row = r.error_rows(c, [item], [pred])[0]
    assert (
        not row["template_wrong"]
        and row["executable_wrong"]
        and row["statement_key_wrong"]
    )
    pred = {
        "decision": "accepted",
        "template": "software",
        "parameters": {"commands": ["matlab", "fsl"]},
    }
    row = r.error_rows(c, [item], [pred])[0]
    assert (
        not row["template_wrong"]
        and not row["executable_wrong"]
        and row["statement_key_wrong"]
    )


def test_null_length_answer_is_empty_and_never_resampled(tmp_path):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "observed-flash",
                "choices": [{"finish_reason": "length", "message": {"content": None}}],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 2048,
                    "total_tokens": 2059,
                },
            },
        )

    adapter = p.Provider(
        p.Config(base_url="https://gateway.invalid/v1", api_key=SECRET),
        tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert call(adapter) == "" and call(adapter) == ""
    assert adapter.stats()["http_attempts"] == 1
    assert adapter.stats()["length_limited_responses"] == 1
    assert adapter.stats()["total_tokens"] == 2059
    # Replay a record written by the initial adapter: retain the raw event and
    # interpret its normal length exhaustion without another paid request.
    events = [json.loads(x) for x in adapter.ledger.read_text().splitlines()]
    events[-1]["status"] = "invalid_response"
    events[-1].pop("text")
    adapter.ledger.write_text("\n".join(json.dumps(x) for x in events) + "\n")
    replay, sent = provider(tmp_path)
    assert call(replay) == "" and sent == []
    assert replay.stats()["historical_null_length_responses"] == 1
    assert replay.stats()["successful_requests"] == 1
