"""Round 18: frozen independent test and transport-only development repair.

No algorithm, threshold, prompt, vocabulary, or historical answer is changed.
All new HTTP attempts (including retries) share a single 600-attempt ledger.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.knowledge import provider_llm as transport
from tools.knowledge import run_condition_canonicalization as base
from tools.knowledge import run_condition_canonicalization_v2 as v2

ARMS = (*v2.ARMS, "retrieval_only")
GOLD_SHA = "e34d6796259e87f44f3bcede9c304eb87b4c1a5e31605cdfd357085bdac45135"
PENDING = [1003, 1004, 1017, 1019, 1023, 1041]
CAP = 600
BOOTSTRAP_SEED = 20261023
BOOTSTRAP_REPLICATES = 2000


def verify_gold(root=ROOT):
    path = root / "evaluation/condition_gold/gold_test_v1.json"
    assert base.sha256(path) == GOLD_SHA, "Frozen gold changed"
    gold = json.loads(path.read_text(encoding="utf-8"))
    packet = root / "evaluation/condition_test_v1/claude_annotation_packet"
    manifest = json.loads((packet / "HANDOFF_MANIFEST.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files"].items():
        assert base.sha256(packet / name) == digest, name
    unlabelled = json.loads((packet / "statements_unlabelled.json").read_text(encoding="utf-8"))
    assert len(gold["items"]) == 45
    assert [i["id"] for i in gold["items"]] == list(range(1001, 1046))
    assert [i["id"] for i in gold["items"] if i["pending_user_decision"]] == PENDING
    for item, original in zip(gold["items"], unlabelled["items"]):
        assert all(item[k] == value for k, value in original.items()), item["id"]
        text = (packet / "sources" / (item["source_id"] + ".txt")).read_text(encoding="utf-8")
        span = item["source_span"]
        assert hashlib.sha256(text.encode()).hexdigest() == span["text_sha256"]
        assert text[span["start"]:span["end"]] == item["quote"]
    gold["slots"] = unlabelled["slots"]  # In-memory input only; frozen bytes are immutable.
    return gold


class HistoricalAnswers:
    """Read-only response replay: successful responses, including invalid JSON, survive."""
    def __init__(self, ledger):
        self.events = [json.loads(line) for line in Path(ledger).read_text(encoding="utf-8").splitlines()]
        self.starts = {e["request_id"]: e for e in self.events if e["event"] == "start"}
        self.answers = {}
        for e in self.events:
            if e["event"] == "end" and e.get("status") == "ok":
                self.answers[e["logical_id"]] = e

    def get(self, arm, item_id, sample, prompt):
        logical = f"{arm}:{item_id}:{sample}"
        event = self.answers.get(logical)
        if event is None:
            return None
        start = self.starts[event["request_id"]]
        assert start["prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
        return event

    def repair_map(self, predictions):
        rows = []
        for p in predictions:
            if p["decision"] != "provider_error":
                continue
            for sample in range(1, 6):
                logical = f"full_v2:{p['id']}:{sample}"
                if logical not in self.answers:
                    attempted = any(e.get("logical_id") == logical for e in self.starts.values())
                    rows.append({"id": p["id"], "sample": sample, "historical_logical_id": logical,
                                 "reason": "failed_interface_sample" if attempted else "not_started_after_early_abort"})
        return rows


class ResilientSamples:
    """Keep K vote positions and continue after an unavailable sample.

    At most one interface supplemental SAMPLE and one length supplemental SAMPLE
    per arm/statement. Each logical sample uses the unchanged metered adapter's
    maximum three HTTP attempts; all attempts count against the shared cap.
    Exhausted interface positions contribute no parsed vote, never an advisory
    vote. Valid/empty/invalid semantic answers are never resampled.
    """
    def __init__(self, provider, arm, item_id, history=None):
        self.provider, self.arm, self.item_id = provider, arm, item_id
        self.history = history
        self.nominal = self.interface_replacements = self.length_replacements = 0
        self.records, self.failures, self.missing = [], [], []

    def receive(self, prompt, sample, replacement_of=None):
        if self.history is not None and isinstance(sample, int):
            old = self.history.get("full_v2", self.item_id, sample, prompt)
            if old is not None:
                self.records.append({"sample": sample, "historical": True,
                                     "replacement_of": None, "request_id": old["request_id"],
                                     "status": old["status"], "finish_reason": old.get("finish_reason"),
                                     "text_sha256": hashlib.sha256(old["text"].encode()).hexdigest()})
                return old["text"], old
        try:
            with transport.scope(self.arm, self.item_id, sample):
                answer = self.provider.complete(prompt)
        except transport.ProviderFailure as error:
            if any(f"HTTP {s}" in str(error) for s in [400, 401, 403, 422]):
                raise
            meta = self.provider.response_info(self.arm, self.item_id, sample)
            self.failures.append({"sample": sample, "replacement_of": replacement_of,
                                  "error_summary": str(error), **meta})
            return None, meta
        meta = self.provider.response_info(self.arm, self.item_id, sample)
        self.records.append({"sample": sample, "replacement_of": replacement_of,
                             "historical": False, **meta})
        return answer, meta

    def __call__(self, prompt):
        self.nominal += 1
        position = self.nominal
        answer, meta = self.receive(prompt, position)
        if answer is None and self.interface_replacements == 0:
            self.interface_replacements += 1
            answer, meta = self.receive(prompt, f"interface_replacement_{position}", position)
        if answer is not None and meta.get("finish_reason") == "length" and self.length_replacements == 0:
            self.length_replacements += 1
            original = answer
            answer, meta = self.receive(prompt, f"length_replacement_{position}", position)
            if answer is None and self.interface_replacements == 0:
                self.interface_replacements += 1
                answer, meta = self.receive(prompt, f"interface_for_length_{position}", position)
            if answer is None:
                # Retain the actual received truncated answer if its replacement fails.
                answer = original
        if answer is None:
            self.missing.append(position)
            return ""
        return answer

    def public(self):
        return {"nominal_samples": self.nominal,
                "interface_replacements": self.interface_replacements,
                "truncation_replacements": self.length_replacements,
                "unavailable_positions": self.missing,
                "interface_failures": self.failures, "responses": self.records}


def predict_one(c, item, texts, slots, vocab, arm, provider, history=None):
    if arm == "retrieval_only":
        p = base.predict(c, item, "", slots, arm, None)
        return {"id": item["id"], "method": item["method"], **p, "sampling": {}}
    caller = ResilientSamples(provider, arm, item["id"], history)
    algorithm_arm = "full_v2" if history is not None else arm
    try:
        p = v2.predict(c, item, texts[item["method"]][item["source_id"]],
                       slots, vocab, algorithm_arm, caller)
        if caller.missing and len(caller.missing) == caller.nominal:
            p = {"decision": "provider_error", "template": None, "parameters": None,
                 "error_summary": "No received sample after the permitted interface supplement"}
    except (TypeError, ValueError, KeyError, AttributeError) as error:
        p = {"decision": "inference_error", "template": None, "parameters": None,
             "runtime_error_type": type(error).__name__}
    return {"id": item["id"], "method": item["method"], **p, "sampling": caller.public()}


def freeze_inputs(c, config, history_path, old_dir, workers):
    gold = verify_gold()
    dev_path = ROOT / "evaluation/condition_gold/gold_reviewed_v1.json"
    dev = json.loads(dev_path.read_text(encoding="utf-8"))
    old_path = old_dir / "predictions_full_v2.json"
    previous = json.loads(old_path.read_text(encoding="utf-8"))
    history = HistoricalAnswers(history_path)
    repair = history.repair_map(previous)
    assert sorted({r["id"] for r in repair}) == [1, 2, 6, 11, 14, 15, 16, 19]
    assert len(repair) == 24 and sum(r["reason"] == "failed_interface_sample" for r in repair) == 8
    vocab, vocab_hashes = v2.load_vocab()
    old_frozen = json.loads((old_dir / "frozen.json").read_text(encoding="utf-8"))
    assert config.public() == old_frozen["provider"]
    assert vocab == old_frozen["vocabulary"] and dev["slots"] == gold["slots"]
    texts, source_hashes = {}, {}
    for dataset, extractions in [(gold, ROOT / "evaluation/condition_test_v1/method_extractions"),
                                 (dev, ROOT / "knowledge/method_extractions")]:
        for method in sorted({i["method"] for i in dataset["items"]}):
            texts[method] = base.sources(extractions, method)
            source_hashes[str((extractions / (method + ".input.json")).relative_to(ROOT))] = base.sha256(extractions / (method + ".input.json"))
    for item in gold["items"]:
        assert item["quote"] in texts[item["method"]][item["source_id"]]
    code = [base.BACKEND / "analysis_condition_canonicalizer.py", Path(__file__),
            Path(transport.__file__), Path(v2.__file__), Path(base.__file__),
            ROOT / "tools/knowledge/condition_evaluation_statistics.py"]
    algorithm_rel = str(code[0].relative_to(ROOT)).replace("\\", "/")
    assert base.sha256(code[0]) == old_frozen["code_sha256"][algorithm_rel]
    frozen = {"schema": "primatex.condition_test_run.v1", "split": "independent_test",
              "gold_sha256": GOLD_SHA,
              "gold_freeze": json.loads((ROOT / "evaluation/condition_gold/gold_test_v1.freeze.json").read_text(encoding="utf-8")),
              "pending_ids": PENDING, "arms": list(ARMS), "provider": config.public(),
              "vocabulary": vocab, "vocabulary_sha256": vocab_hashes, "slots": gold["slots"],
              "code_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): base.sha256(p) for p in code},
              "parameters": {n: getattr(c, n) for n in ["RHO_MIN", "SAMPLES", "V2_SUPPORT", "V2_MARGIN"]},
              "source_sha256": source_hashes, "workers": workers,
              "shared_http_cap": CAP, "test_nominal_positions": 315,
              "development_repair_positions": repair,
              "historical_ledger_sha256": base.sha256(history_path),
              "historical_prediction_sha256": base.sha256(old_path),
              "development_gold_sha256": base.sha256(dev_path),
              "retry_policy": ResilientSamples.__doc__,
              "transport_pacing": old_frozen["transport_pacing"],
              "statistics": {"bootstrap_replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED,
                  "interval": "statement paired percentile bootstrap, linear 2.5/97.5 percentiles",
                  "canonical_key_metric": "unchanged scorer: unique (method,key) sets recomputed in every resample; repeats collapse in key sets",
                  "zero_denominator": "precision/recall/f1=0, as in development",
                  "mcnemar": "two-sided exact binomial; per-statement expected vs accepted parameterised canonical key; advisory gold has key None; non-accepted has key None (same as historical error_rows); both 45 and 39 statements",
                  "multiple_comparisons": "two preregistered comparisons, unadjusted exact p; no tuning"}}
    return gold, dev, previous, history, texts, vocab, frozen


def usage_rows(provider):
    ends = {e["request_id"]: e for e in provider.events if e["event"] == "end"}
    columns = ["ordinal", "arm", "item_id", "sample", "attempt", "request_id", "status", "http_status", "finish_reason", "input_tokens", "output_tokens", "total_tokens", "reasoning_content_present", "reasoning_tokens"]
    return [{k: (s if k in s else ends.get(s["request_id"], {})).get(k) for k in columns}
            for s in provider.events if s["event"] == "start"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--provider-config", required=True)
    ap.add_argument("--historical-ledger", required=True)
    ap.add_argument("--old-dir", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    assert 1 <= args.workers <= 4
    config = transport.load_config(args.provider_config, model="deepseek-v4.1-flash", temperature=0.7,
                                   max_tokens=8192, thinking="disabled", json_output=True, timeout=180)
    c = base.load_canon()
    gold, dev, previous, history, texts, vocab, frozen = freeze_inputs(c, config, Path(args.historical_ledger), Path(args.old_dir), args.workers)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with base.run_lock(out):
        digest = base.freeze_or_verify(out, frozen, args.resume)
        if args.prepare_only:
            print(json.dumps({"status": "frozen", "frozen_sha256": digest, "gold_sha256": GOLD_SHA,
                              "test_nominal": 315, "dev_repair_nominal": 24, "shared_http_cap": CAP}), flush=True)
            return
        provider = transport.Provider(config, out / "requests", CAP, minimum_interval=2.0)
        try:
            predictions = {}
            phases = [(arm, gold, None) for arm in ARMS]
            phases += [("dev_full_v2_repair", dev, history)]
            for arm, dataset, historical in phases:
                selected = dataset["items"] if historical is None else [i for i in dev["items"] if i["id"] in {r["id"] for r in frozen["development_repair_positions"]}]
                phase_predictions = {}
                def one(item):
                    path = out / "checkpoints" / f"{arm}_{item['id']}.json"
                    if path.exists():
                        checkpoint = json.loads(path.read_text(encoding="utf-8"))
                        assert checkpoint["frozen_sha256"] == digest
                        return checkpoint["prediction"]
                    p = predict_one(c, item, texts, dataset["slots"], vocab, arm, provider, historical)
                    base.save_json(path, {"frozen_sha256": digest, "prediction": p})
                    return p
                started = time.monotonic()
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futures = [pool.submit(one, item) for item in selected]
                    for done, future in enumerate(as_completed(futures), 1):
                        p = future.result()
                        phase_predictions[p["id"]] = p
                        print(f"{arm}: {done}/{len(selected)}; HTTP={provider.stats()['http_attempts']}", flush=True)
                ordered = [phase_predictions[i["id"]] for i in selected]
                if historical is not None:
                    ordered = [phase_predictions.get(p["id"], p) for p in previous]
                    assert sum(a != b for a, b in zip(ordered, previous)) == 8
                predictions[arm] = ordered
                base.save_json(out / f"predictions_{arm}.json", ordered)
                base.save_json(out / f"phase_{arm}.json", {"completed_at": datetime.now(timezone.utc).isoformat(),
                               "elapsed_seconds_this_execution": time.monotonic() - started,
                               "usage": provider.stats(arm)})
            base.write_csv(out / "call_usage.csv", usage_rows(provider))
            base.save_json(out / "usage.json", provider.stats())
            failures = [{"arm": arm, "id": p["id"], "interface_failures": p["sampling"].get("interface_failures", []),
                         "unavailable_positions": p["sampling"].get("unavailable_positions", []),
                         "interface_replacements": p["sampling"].get("interface_replacements", 0)}
                        for arm, preds in predictions.items() for p in preds
                        if p.get("sampling", {}).get("interface_failures") or p.get("sampling", {}).get("unavailable_positions")]
            base.save_json(out / "interface_failures.json", failures)
            from tools.knowledge.condition_evaluation_statistics import write_reports
            write_reports(c, out, gold, dev, predictions, previous, provider, digest)
            base.save_json(out / "run_status.json", {"status": "completed", "frozen_sha256": digest,
                           "gold_sha256": GOLD_SHA, "usage": provider.stats(), "analysis_runs": 0,
                           "preprocessing_submissions": 0, "deployment_or_restart": False,
                           "reserved_groups_touched": False})
            print(json.dumps({"status": "completed", "usage": provider.stats()}), flush=True)
        finally:
            provider.close()


if __name__ == "__main__":
    main()
