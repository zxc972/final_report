"""Read-only Round 17 audit. Never calls any model or modifies a prediction."""

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.knowledge import provider_llm as t
from tools.knowledge import run_condition_canonicalization as base
from tools.knowledge import run_condition_canonicalization_v2 as run
from tools.knowledge import prepare_condition_test_cards as cards


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def ledger(folder):
    events = [
        json.loads(line)
        for line in (folder / "requests/calls.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    starts = [e for e in events if e["event"] == "start"]
    ends = {e["request_id"]: e for e in events if e["event"] == "end"}
    assert len({e["request_id"] for e in starts}) == len(starts)
    assert all(e["request_id"] in ends for e in starts), "Unaccounted request"
    return events, starts, ends


class ReadOnlyReplay:
    def __init__(self, events):
        self.events = events

    def complete(self, prompt):
        scope = t._SCOPE.get()
        assert scope is not None
        selected = [
            e for e in self.events if e.get("logical_id") == scope["logical_id"]
        ]
        starts = [e for e in selected if e["event"] == "start"]
        for e in starts:
            assert hashlib.sha256(prompt.encode()).hexdigest() == e["prompt_sha256"]
        good = [e for e in selected if e["event"] == "end" and e["status"] == "ok"]
        if good:
            return good[-1].get("text", "")
        raise t.ProviderFailure("Recorded provider failure; no HTTP permitted")

    def response_info(self, arm, item_id, sample):
        ends = [
            e
            for e in self.events
            if e["event"] == "end"
            and e.get("logical_id") == f"{arm}:{item_id}:{sample}"
        ]
        assert ends
        return {
            key: ends[-1].get(key)
            for key in [
                "request_id",
                "finish_reason",
                "status",
                "reasoning_content_present",
                "reasoning_tokens",
            ]
        }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--independent", required=True)
    ap.add_argument("--provider-config", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    independent = Path(args.independent)
    frozen = json.loads((out / "frozen.json").read_text())
    assert (
        base.sha256(out / "frozen.json") == (out / "frozen.sha256").read_text().strip()
    )
    gold_path = ROOT / "evaluation/condition_gold/gold_reviewed_v1.json"
    assert base.sha256(gold_path) == frozen["gold_sha256"]
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    c = base.load_canon()
    for path, sha in frozen["code_sha256"].items():
        assert base.sha256(ROOT / path) == sha, path
    vocab, hashes = run.load_vocab()
    assert vocab == frozen["vocabulary"] and hashes == frozen["vocabulary_sha256"]
    texts = {}
    for path, sha in frozen["source_sha256"].items():
        file = ROOT / "knowledge/method_extractions" / path
        assert base.sha256(file) == sha
        texts[path.removesuffix(".input.json")] = base.sources(
            file.parent, path.removesuffix(".input.json")
        )
    for arm, sha in frozen["v1_prediction_sha256"].items():
        assert (
            base.sha256(
                ROOT / "results/condition_canon_draft_v1" / f"predictions_{arm}.json"
            )
            == sha
        )
    events, starts, ends = ledger(out)
    ievents, istarts, iends = ledger(independent)
    assert (
        len(starts) <= 1188
        and len(istarts) <= 12
        and len(starts) + len(istarts) <= 1200
    )
    for h in sorted((out / "freeze_history").glob("*/continuation.json")):
        history = json.loads(h.read_text())
        prefix = (out / "requests/calls.jsonl").read_bytes()[
            : history["ledger_prefix_bytes"]
        ]
        assert hashlib.sha256(prefix).hexdigest() == history["ledger_prefix_sha256"]
        for name, sha in history["retained_prediction_sha256"].items():
            assert (
                digest(
                    json.loads((out / "checkpoints" / name).read_text())["prediction"]
                )
                == sha
            )
    replay = ReadOnlyReplay(events)
    verified = 0
    summary = json.loads((out / "summary.json").read_text())
    for arm in run.ARMS:
        preds = json.loads((out / f"predictions_{arm}.json").read_text())
        assert [p["id"] for p in preds] == [i["id"] for i in gold["items"]]
        for item, pred in zip(gold["items"], preds):
            caller = run.SampleCaller(replay, arm, item["id"])
            try:
                actual = run.predict(
                    c,
                    item,
                    texts[item["method"]][item["source_id"]],
                    gold["slots"],
                    vocab,
                    arm,
                    caller,
                )
            except t.ProviderFailure:
                assert pred["decision"] == "provider_error"
                actual = None
            except (TypeError, ValueError, KeyError, AttributeError):
                assert pred["decision"] == "inference_error"
                actual = None
            if actual is not None:
                saved = {
                    k: v
                    for k, v in pred.items()
                    if k not in {"id", "method", "sampling"}
                }
                assert actual == saved, (arm, item["id"])
            assert caller.public() == pred["sampling"]
            assert caller.replacements <= 1
            verified += 1
        metrics = base.score_with_details(c, gold["items"], preds)
        for key, value in metrics.items():
            assert summary[arm][key] == value
    for arm in ["full", "k1", "retrieval_only", "direct"]:
        preds = json.loads(
            (
                ROOT / "results/condition_canon_draft_v1" / f"predictions_{arm}.json"
            ).read_text()
        )
        metrics = base.score_with_details(c, gold["items"], preds)
        for key, value in metrics.items():
            assert summary["v1_" + arm][key] == value
        assert summary["v1_" + arm]["new_model_calls"] == 0
    by_id = {i["id"]: i for i in gold["items"]}
    for e in starts:
        assert e["arm"] in run.ARMS
        prompt = run.prompt_for(
            c, by_id[e["item_id"]], gold["slots"], vocab, direct=e["arm"] == "direct_v2"
        )
        assert "gold_template" not in prompt and "review_note" not in prompt
        assert hashlib.sha256(prompt.encode()).hexdigest() == e["prompt_sha256"]
        assert e["model"] == "deepseek-v4.1-flash" and e["temperature"] == 0.7
        assert e["settings"]["max_tokens"] == 8192 and e["settings"]["thinking"] == {
            "type": "disabled"
        }
        assert e["settings"]["response_format"] == {"type": "json_object"}
    method_by_id = {m["method_id"]: m for m in cards.METHODS}
    for e in istarts:
        assert e["arm"] == "independent_card_extraction"
        payload = json.loads(
            (
                independent / "method_extractions" / (e["item_id"] + ".input.json")
            ).read_text()
        )
        prompt = (
            cards.PROMPT + "\nINPUT JSON:\n" + json.dumps(payload, ensure_ascii=False)
        )
        assert hashlib.sha256(prompt.encode()).hexdigest() == e["prompt_sha256"]
        assert "gold_template" not in prompt
    source_manifest = json.loads((independent / "source_manifest.json").read_text())
    for source in source_manifest:
        assert (
            base.sha256(independent / "sources" / (source["source_id"] + ".txt"))
            == source["text_sha256"]
        )
    packet = independent / "claude_annotation_packet"
    handoff = json.loads((packet / "HANDOFF_MANIFEST.json").read_text())
    for name, sha in handoff["files"].items():
        assert base.sha256(packet / name) == sha
    unlabelled = json.loads((packet / "statements_unlabelled.json").read_text())
    assert all(not any(k.startswith("gold_") for k in i) for i in unlabelled["items"])
    with (packet / "annotation_sheet.csv").open(encoding="utf-8-sig", newline="") as f:
        assert all(
            not row["gold_template"] and not row["gold_parameters"]
            for row in csv.DictReader(f)
        )
    quote_count = 0
    for method in cards.METHODS:
        card = json.loads(
            (
                independent / "method_extractions" / (method["method_id"] + ".json")
            ).read_text()
        )
        for field in cards.FIELDS:
            for claim in card[field]:
                text = (
                    independent / "sources" / (claim["source_id"] + ".txt")
                ).read_text(encoding="utf-8")
                span = claim["source_span"]
                assert text[span["start"] : span["end"]] == claim["quote"]
                assert hashlib.sha256(text.encode()).hexdigest() == span["text_sha256"]
                quote_count += 1
    source_split = json.loads((independent / "source_independence.json").read_text())
    assert not source_split["shared_urls"]
    secret = t.load_config(args.provider_config).api_key.encode()
    checked = 0
    for folder in [out, independent]:
        for path in folder.rglob("*"):
            if path.is_file() and path.name != "run.lock":
                assert secret not in path.read_bytes(), "Credential leakage detected"
                checked += 1
    requests = [ends[s["request_id"]] for s in starts] + [
        iends[s["request_id"]] for s in istarts
    ]
    report = {
        "status": "audited",
        "development_predictions_replayed_without_HTTP": verified,
        "all_prompt_hashes_label_free": True,
        "v1_rescore_new_calls": 0,
        "development_http_attempts": len(starts),
        "independent_card_extraction_http_attempts": len(istarts),
        "total_http_attempts": len(starts) + len(istarts),
        "authorised_http_cap": 1200,
        "known_input_tokens": sum(e.get("input_tokens") or 0 for e in requests),
        "known_output_tokens": sum(e.get("output_tokens") or 0 for e in requests),
        "known_total_tokens": sum(e.get("total_tokens") or 0 for e in requests),
        "unknown_usage_requests": sum(
            any(
                e.get(k) is None
                for k in ["input_tokens", "output_tokens", "total_tokens"]
            )
            for e in requests
        ),
        "http_status_counts": dict(
            collections.Counter(str(e.get("http_status")) for e in requests)
        ),
        "length_responses": sum(e.get("finish_reason") == "length" for e in requests),
        "reasoning_tokens_positive_responses": sum(
            (e.get("reasoning_tokens") or 0) > 0 for e in requests
        ),
        "reasoning_content_present_responses": sum(
            e.get("reasoning_content_present") is True for e in requests
        ),
        "independent_card_quotes_verified": quote_count,
        "independent_annotation_items": len(unlabelled["items"]),
        "independent_shared_source_urls": 0,
        "independent_algorithm_evaluation_calls": 0,
        "secret_scanned_files": checked,
        "secret_matches": 0,
        "gold_test_labels_created": False,
        "frozen_sha256": base.sha256(out / "frozen.json"),
    }
    base.save_json(out / "audit.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
