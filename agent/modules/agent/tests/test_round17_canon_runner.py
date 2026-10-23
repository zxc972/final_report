"""Round 17 evaluation boundaries: no labels, exact ablations and bounded replacement."""

import importlib.util
import json
from pathlib import Path
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.knowledge import provider_llm as t
from tools.knowledge import run_condition_canonicalization_v2 as r

c = r.base.load_canon()
SECRET = "round17-test-secret-never-log"
ITEM = {
    "id": 1,
    "method": "m",
    "field": "inputs",
    "statement": "Required T1 input",
    "quote": "A T1 image is required.",
    "source_id": "source",
    "gold_template": "DO_NOT_SEND_GOLD",
    "gold_parameters": {"private": "DO_NOT_SEND_GOLD"},
}
SLOTS = {"T1": ["space"]}
VOCAB = {"types": ["type:Volume.T1"], "steps": ["recon-all"]}


def adapter(tmp_path, finishes):
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        reason = finishes[min(len(bodies) - 1, len(finishes) - 1)]
        return httpx.Response(
            200,
            json={
                "model": "small-flash",
                "choices": [
                    {
                        "finish_reason": reason,
                        "message": {
                            "content": (
                                None
                                if reason == "length"
                                else '{"template":"advisory"}'
                            ),
                            "reasoning_content": "",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                    "completion_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    config = t.Config(
        base_url="https://gateway.invalid/v1",
        api_key=SECRET,
        max_tokens=8192,
        thinking="disabled",
        json_output=True,
    )
    return t.Provider(config, tmp_path, 1188, client=client), bodies


def test_v2_payload_and_observed_metadata_are_auditable(tmp_path):
    provider, bodies = adapter(tmp_path, ["stop"])
    caller = r.SampleCaller(provider, "full_v2", 1)
    caller("Return JSON")
    assert bodies[0]["thinking"] == {"type": "disabled"}
    assert bodies[0]["response_format"] == {"type": "json_object"}
    assert bodies[0]["max_tokens"] == 8192 and bodies[0]["temperature"] == 0.7
    meta = caller.records[0]
    assert meta["reasoning_tokens"] == 0 and not meta["reasoning_content_present"]
    assert SECRET not in provider.ledger.read_text()
    provider.close()


def test_only_one_truncation_replacement_and_resume_is_free(tmp_path):
    provider, bodies = adapter(
        tmp_path, ["length", "stop", "length", "stop", "stop", "stop"]
    )
    caller = r.SampleCaller(provider, "full_v2", 1)
    first = r.predict(c, ITEM, ITEM["quote"], SLOTS, VOCAB, "full_v2", caller)
    assert first["decision"] == "advisory" and first["support"] == 0.8
    assert caller.nominal == 5 and caller.replacements == 1 and len(bodies) == 6
    assert provider.stats()["length_limited_responses"] == 2
    assert provider.stats()["total_tokens"] == 72
    replay = r.SampleCaller(provider, "full_v2", 1)
    assert r.predict(c, ITEM, ITEM["quote"], SLOTS, VOCAB, "full_v2", replay) == first
    assert len(bodies) == 6 and replay.replacements == 1
    assert len({e["logical_id"] for e in provider.events if e["event"] == "start"}) == 6
    provider.close()


def test_truncated_replacement_is_not_replaced_again(tmp_path):
    provider, bodies = adapter(
        tmp_path, ["length", "length", "stop", "stop", "stop", "stop"]
    )
    caller = r.SampleCaller(provider, "full_v2", 1)
    r.predict(c, ITEM, ITEM["quote"], SLOTS, VOCAB, "full_v2", caller)
    assert len(bodies) == 6 and caller.replacements == 1
    provider.close()


def test_group_sample_counts_fields_and_labels_not_in_prompts():
    for arm, n in [("full_v2", 5), ("k1_v2", 1), ("direct_v2", 1)]:
        prompts = []

        def llm(prompt):
            prompts.append(prompt)
            return '{"template":"advisory"}'

        r.predict(c, ITEM, ITEM["quote"], SLOTS, VOCAB, arm, llm)
        assert len(prompts) == n
        assert all("Field in the method card: inputs" in p for p in prompts)
        assert all("DO_NOT_SEND_GOLD" not in p and "private" not in p for p in prompts)
        if arm == "direct_v2":
            assert all(
                "Allowed product types" not in p and "Allowed processing steps" not in p
                for p in prompts
            )
        else:
            assert all("type:Volume.T1" in p and "recon-all" in p for p in prompts)


def test_direct_does_not_apply_vocabulary_normalisation_or_type_check():
    answer = (
        lambda _: '{"template":"product_present","parameters":{"slot":"T1","type":"mesh"}}'
    )
    direct = r.predict(c, ITEM, ITEM["quote"], SLOTS, VOCAB, "direct_v2", answer)
    full = r.predict(c, ITEM, ITEM["quote"], SLOTS, VOCAB, "full_v2", answer)
    assert direct["decision"] == "accepted" and direct["parameters"]["type"] == "mesh"
    assert full["decision"] == "review" and full["invalid_attempts"] == {
        "product_present": 5
    }


def test_vocab_is_entire_declared_type_and_step_set():
    vocab, hashes = r.load_vocab()
    folder = ROOT / "agent/modules/agent/knowledge_analysis"
    types = json.loads((folder / "product_types.json").read_text())
    steps = json.loads((folder / "workflow_steps.json").read_text())
    assert set(vocab["types"]) == {a["id"] for a in types["types"]}
    assert set(vocab["steps"]) == {a["id"] for a in steps["steps"]} | {"recon-all"}
    assert len(hashes) == 2


def test_v1_rescore_reads_unchanged_predictions_without_provider(tmp_path, monkeypatch):
    gold = {
        "items": [
            {
                "id": 1,
                "method": "m",
                "gold_template": "advisory",
                "gold_parameters": None,
            }
        ]
    }
    for arm in ["full", "k1", "retrieval_only", "direct"]:
        (tmp_path / f"predictions_{arm}.json").write_text(
            json.dumps(
                [
                    {
                        "id": 1,
                        "method": "m",
                        "template": "advisory",
                        "decision": "advisory",
                        "parameters": None,
                    }
                ]
            )
        )

    def forbid(*a, **k):
        raise AssertionError("Rescoring must not call a provider")

    monkeypatch.setattr(t, "Provider", forbid)
    before = {p.name: r.base.sha256(p) for p in tmp_path.glob("predictions_*.json")}
    result = r.rescore_v1(c, gold, tmp_path, tmp_path)
    assert all(
        m["template_accuracy"] == 1 and m["new_model_calls"] == 0
        for m in result.values()
    )
    assert before == {
        p.name: r.base.sha256(p) for p in tmp_path.glob("predictions_*.json")
    }


def test_round17_budget_reserves_separate_extraction_cap(tmp_path):
    assert r.DEV_CAP + r.EXTRACTION_CAP == 1200
    cfg = t.Config(base_url="https://gateway.invalid/v1", api_key=SECRET)
    assert "thinking" not in cfg.public() and "response_format" not in cfg.public()
    with pytest.raises(ValueError, match="1200"):
        t.Provider(cfg, tmp_path, 1201)


def test_departure_pacing_applies_to_different_logical_calls(tmp_path, monkeypatch):
    now = [0.0]
    departures = []
    monkeypatch.setattr(t.time, "monotonic", lambda: now[0])

    def sleep(delay):
        now[0] += delay

    def handler(request):
        departures.append(now[0])
        return httpx.Response(
            200,
            json={
                "model": "small-flash",
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
            },
        )

    cfg = t.Config(base_url="https://gateway.invalid/v1", api_key=SECRET)
    provider = t.Provider(
        cfg,
        tmp_path,
        4,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleep,
        minimum_interval=2,
    )
    for item in range(3):
        with t.scope("full_v2", item, 1):
            provider.complete("Return JSON")
    assert departures == [0.0, 2.0, 4.0]
    provider.close()
