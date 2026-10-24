"""Offline audit of Round18: no transport client, HTTP, model, or label edits."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.knowledge import run_condition_test_evaluation as run
from tools.knowledge import condition_evaluation_statistics as statistics
base, v2, transport = run.base, run.v2, run.transport


class ReadOnlyReplay:
    def __init__(self, events, failure_messages):
        self.events, self.failure_messages = events, failure_messages
        self.calls = []

    def complete(self, prompt):
        logical = transport._SCOPE.get()["logical_id"]
        self.calls.append(logical)
        events = [e for e in self.events if e.get("logical_id") == logical]
        for e in events:
            if e["event"] == "start":
                assert e["prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
        ends = [e for e in events if e["event"] == "end"]
        ok = [e for e in ends if e["status"] == "ok"]
        if ok:
            return ok[-1]["text"]
        assert logical in self.failure_messages, ("unrecorded unavailable sample", logical)
        raise transport.ProviderFailure(self.failure_messages[logical])

    def response_info(self, arm, item_id, sample):
        logical = f"{arm}:{item_id}:{sample}"
        ends = [e for e in self.events if e["event"] == "end" and e.get("logical_id") == logical]
        return {key: ends[-1].get(key) for key in ["request_id", "finish_reason", "status", "reasoning_content_present", "reasoning_tokens"]} if ends else {}



def verify_intervals_independently(c, items, predictions, expected):
    """NumPy confusion arrays/key sets, independent of the original score function."""
    import numpy as np
    import random
    prepared = {}
    for arm, preds in predictions.items():
        prepared[arm] = {
            "gold": np.array([i["gold_template"] != "advisory" for i in items]),
            "pred": np.array([p.get("decision") == "accepted" and p.get("template") != "advisory" for p in preds]),
            "template": np.array([i["gold_template"] == p.get("template") for i, p in zip(items, preds)]),
            "review": np.array([p.get("decision") == "review" for p in preds]),
            "gold_keys": [(i["method"], c.canonical_key(i["gold_template"], i["gold_parameters"] or {})) if i["gold_template"] != "advisory" else None for i in items],
            "pred_keys": [(i["method"], c.canonical_key(p["template"], p["parameters"])) if p.get("decision") == "accepted" and p.get("parameters") is not None and p.get("template") != "advisory" else None for i, p in zip(items, preds)],
        }
    def three(tp, fp, fn):
        precision = tp / (tp + fp) if tp + fp else 0.
        recall = tp / (tp + fn) if tp + fn else 0.
        return [precision, recall, 2 * precision * recall / (precision + recall) if precision + recall else 0.]
    def calculate(data, indices):
        g, p = data["gold"][indices], data["pred"][indices]
        tp, fp, fn, tn = [int(x.sum()) for x in [g & p, ~g & p, g & ~p, ~g & ~p]]
        gk = {data["gold_keys"][j] for j in indices} - {None}
        pk = {data["pred_keys"][j] for j in indices} - {None}
        ktp = len(gk & pk)
        return [float(data["template"][indices].mean()), *three(tp, fp, fn),
                *three(tn, fn, fp), *three(ktp, len(pk) - ktp, len(gk) - ktp),
                int(data["review"][indices].sum())]
    seed, reps = expected["seed"], expected["replicates"]
    rng = random.Random(seed)
    draws = [rng.choices(range(len(items)), k=len(items)) for _ in range(reps)]
    for arm, data in prepared.items():
        estimates = calculate(data, list(range(len(items))))
        distribution = np.array([calculate(data, sample) for sample in draws])
        low, high = np.quantile(distribution, [.025, .975], axis=0, method="linear")
        for j, metric in enumerate(statistics.METRICS):
            ci = expected["arms"][arm]["intervals_95"][metric]
            assert np.allclose([ci["estimate"], ci["low"], ci["high"]],
                               [estimates[j], low[j], high[j]], rtol=1e-12, atol=1e-12), (arm, metric)
    return len(prepared) * len(statistics.METRICS)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--old-dir", required=True)
    ap.add_argument("--historical-ledger", required=True)
    ap.add_argument("--provider-config", required=True, help="Read only to scan publication for the exact credential; never output it")
    args = ap.parse_args()
    out, old_dir = Path(args.out), Path(args.old_dir)
    frozen = json.loads((out / "frozen.json").read_text(encoding="utf-8"))
    digest = base.sha256(out / "frozen.json")
    assert (out / "frozen.sha256").read_text().strip() == digest
    assert frozen["gold_sha256"] == run.GOLD_SHA
    for name, expected in frozen["code_sha256"].items():
        assert base.sha256(ROOT / name) == expected, ("code changed", name)
    for name, expected in frozen["source_sha256"].items():
        assert base.sha256(ROOT / name) == expected
    gold = run.verify_gold()
    dev = json.loads((ROOT / "evaluation/condition_gold/gold_reviewed_v1.json").read_text(encoding="utf-8"))
    assert base.sha256(ROOT / "evaluation/condition_gold/gold_reviewed_v1.json") == frozen["development_gold_sha256"]
    assert base.sha256(args.historical_ledger) == frozen["historical_ledger_sha256"]
    assert base.sha256(old_dir / "predictions_full_v2.json") == frozen["historical_prediction_sha256"]
    previous = json.loads((old_dir / "predictions_full_v2.json").read_text(encoding="utf-8"))
    history = run.HistoricalAnswers(args.historical_ledger)
    assert history.repair_map(previous) == frozen["development_repair_positions"]
    vocab, vocab_sha = v2.load_vocab()
    assert vocab == frozen["vocabulary"] and vocab_sha == frozen["vocabulary_sha256"]
    old_frozen = json.loads((old_dir / "frozen.json").read_text(encoding="utf-8"))
    assert old_frozen["provider"] == frozen["provider"]
    assert gold["slots"] == dev["slots"] == frozen["slots"]
    c = base.load_canon()
    for name, value in frozen["parameters"].items():
        assert getattr(c, name) == value
    events = [json.loads(s) for s in (out / "requests/calls.jsonl").read_text(encoding="utf-8").splitlines()]
    starts = [e for e in events if e["event"] == "start"]
    ends = {e["request_id"]: e for e in events if e["event"] == "end"}
    assert len(starts) <= 600 and [e["ordinal"] for e in starts] == list(range(1, len(starts) + 1))
    assert len(starts) == len(ends) and {s["request_id"] for s in starts} == set(ends)
    allowed = {*run.ARMS, "dev_full_v2_repair"}
    assert all(s["arm"] in allowed - {"retrieval_only"} for s in starts)
    assert all(s["settings"] == frozen["provider"] for s in starts)
    texts = {}
    for dataset, extractions in [(gold, ROOT / "evaluation/condition_test_v1/method_extractions"),
                                 (dev, ROOT / "knowledge/method_extractions")]:
        for method in {i["method"] for i in dataset["items"]}:
            texts[method] = base.sources(extractions, method)
    predictions = {a: json.loads((out / f"predictions_{a}.json").read_text(encoding="utf-8"))
                   for a in [*run.ARMS, "dev_full_v2_repair"]}
    failure_messages = {f"{arm}:{p['id']}:{f['sample']}": f["error_summary"]
                        for arm, preds in predictions.items() for p in preds
                        for f in p.get("sampling", {}).get("interface_failures", [])}
    replay = ReadOnlyReplay(events, failure_messages)
    checked = 0
    for arm in run.ARMS:
        for item, pred in zip(gold["items"], predictions[arm]):
            assert item["id"] == pred["id"]
            result = run.predict_one(c, item, texts, gold["slots"], vocab, arm, replay)
            assert result == pred, ("prediction replay mismatch", arm, item["id"])
            checked += 1
    selected = {r["id"] for r in frozen["development_repair_positions"]}
    by_id = {i["id"]: i for i in dev["items"]}
    for old, pred in zip(previous, predictions["dev_full_v2_repair"]):
        if old["id"] not in selected:
            assert old == pred
        else:
            result = run.predict_one(c, by_id[old["id"]], texts, dev["slots"], vocab,
                                     "dev_full_v2_repair", replay, history)
            assert result == pred, ("development replay mismatch", old["id"])
    # Every request prompt is reconstructed without access to gold fields.
    test_by_id = {i["id"]: i for i in gold["items"]}
    for start in starts:
        item = by_id[start["item_id"]] if start["arm"] == "dev_full_v2_repair" else test_by_id[start["item_id"]]
        prompt = v2.prompt_for(c, item, gold["slots"], vocab, direct=start["arm"] == "direct_v2")
        assert hashlib.sha256(prompt.encode()).hexdigest() == start["prompt_sha256"]
        stripped = {k: v for k, v in item.items() if not k.startswith("gold_") and k not in ["annotation_note", "pending_user_decision"]}
        assert v2.prompt_for(c, stripped, gold["slots"], vocab, direct=start["arm"] == "direct_v2") == prompt
    formal = {a: predictions[a] for a in run.ARMS}
    primary = statistics.bootstrap(c, gold["items"], formal)
    assert primary == json.loads((out / "metrics_45.json").read_text(encoding="utf-8"))
    indices = [j for j, item in enumerate(gold["items"]) if not item["pending_user_decision"]]
    subset = [gold["items"][j] for j in indices]
    reduced = {a: [preds[j] for j in indices] for a, preds in formal.items()}
    assert statistics.bootstrap(c, subset, reduced) == json.loads((out / "metrics_39.json").read_text(encoding="utf-8"))
    independent_intervals = verify_intervals_independently(c, gold["items"], formal, primary)
    independent_intervals += verify_intervals_independently(c, subset, reduced, json.loads((out / "metrics_39.json").read_text(encoding="utf-8")))
    paired = json.loads((out / "mcnemar.json").read_text(encoding="utf-8"))
    assert paired == {"all_45": statistics.paired_comparisons(c, gold["items"], formal),
                      "nonpending_39": statistics.paired_comparisons(c, subset, reduced)}
    from scipy.stats import binomtest
    scipy_checks = 0
    for split in paired.values():
        for m in split.values():
            expected = binomtest(m["first_only_correct"], m["discordant"], p=.5).pvalue if m["discordant"] else 1.
            assert math.isclose(expected, m["p_exact_two_sided"], rel_tol=1e-12)
            scipy_checks += 1
    # Exact secret scan remains in process memory; neither credential nor raw errors are printed.
    config = transport.load_config(args.provider_config)
    leaks = []
    for folder in [out, ROOT / "evaluation/condition_gold", ROOT / "tools/knowledge"]:
        for p in folder.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                if config.api_key.encode() in p.read_bytes():
                    leaks.append(str(p.relative_to(ROOT)))
    assert not leaks, "Publication contains a configured secret"
    audit = {"status": "audited", "frozen_sha256": digest, "gold_sha256": run.GOLD_SHA,
             "formal_predictions_replayed_without_http": checked, "development_repairs_replayed_without_http": 8,
             "development_other_predictions_unchanged": 100, "prompt_hashes_checked": len(starts),
             "code_and_vocabulary_unchanged": True, "raw_ledger_sha256": base.sha256(out / "requests/calls.jsonl"),
             "historical_ledger_sha256_unchanged": frozen["historical_ledger_sha256"],
             "both_bootstraps_reproduced": True, "independent_numpy_interval_crosschecks": independent_intervals,
             "scipy_binomial_crosschecks": scipy_checks,
             "http_attempts": len(starts), "http_cap": 600, "unfinished_requests": 0,
             "secret_scan_matches": 0, "new_http_calls_in_audit": 0,
             "statistics_sources": ["https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html",
                                    "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html"]}
    base.save_json(out / "audit.json", audit)
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
