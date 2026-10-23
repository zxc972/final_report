"""Run and score algorithm 1 (condition canonicalisation) against the gold set.

Usage (on the server, provider configured):
  python tools/knowledge/run_condition_canonicalization.py \
      --gold evaluation/condition_gold/gold_v1.json \
      --extractions knowledge/method_extractions \
      --llm package.module:function   # callable(prompt:str)->str using the configured provider
      --arms full,k1,retrieval_only,direct --out results/condition_canon_v1

Arms
  full            retrieval top-3 + K=5 samples + type check + voting (algorithm 1)
  k1              same with K=1 (no voting)
  retrieval_only  top-1 retrieved template, no LLM (template-level only)
  direct          one LLM sample offered all templates, no retrieval / type check / voting
Metrics
  template_accuracy      statement-level template label vs gold
  executable P/R/F1      non-advisory vs advisory decision
  key P/R/F1             canonical (method, template, parameters) after merge
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "agent" / "modules" / "agent" / "backend"


def load_canon():
    spec = importlib.util.spec_from_file_location("canon", BACKEND / "analysis_condition_canonicalizer.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["canon"] = mod
    spec.loader.exec_module(mod)
    return mod


def load_llm(ref: str):
    module, func = ref.split(":")
    return getattr(importlib.import_module(module), func)


def sources(extractions: Path, method: str) -> dict:
    path = extractions / f"{method}.input.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {s["source_id"]: s.get("text", "") for s in data.get("sources", [])}


def predict(c, item, source_text, slots, arm, llm):
    st = {"statement": item["statement"], "quote": item["quote"], "source_id": item["source_id"]}
    if arm == "retrieval_only":
        top = c.Retriever().rank(item["statement"] + " " + item["quote"], k=1)[0][0]
        return {"decision": "advisory" if top == "advisory" else "accepted", "template": top, "parameters": None}
    if arm == "direct":
        answer = c.parse_answer(llm(c.build_prompt(item["statement"], item["quote"], list(c.TEMPLATES), slots)))
        if answer is None:
            return {"decision": "advisory", "template": "advisory", "parameters": None}
        return {"decision": "accepted", "template": answer[0], "parameters": answer[1],
                "key": c.canonical_key(*answer), "source_id": item["source_id"], "statement": item["statement"]}
    samples = 1 if arm == "k1" else c.SAMPLES
    r = c.canonicalise_statement(st, source_text, slots, llm, samples=samples)
    if r["decision"] != "accepted":
        r["template"] = r.get("template") if r["decision"] == "review" else "advisory"
    return r


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0, "tp": tp, "fp": fp, "fn": fn}


def score(c, items, preds):
    correct = sum(1 for i, p in zip(items, preds) if p.get("template") == i["gold_template"])
    exe = [(i["gold_template"] != "advisory", p.get("decision") == "accepted" and p.get("template") != "advisory")
           for i, p in zip(items, preds)]
    tp = sum(1 for g, q in exe if g and q); fp = sum(1 for g, q in exe if q and not g); fn = sum(1 for g, q in exe if g and not q)
    gold_keys, pred_keys = set(), set()
    for i, p in zip(items, preds):
        if i["gold_template"] != "advisory":
            gold_keys.add((i["method"], c.canonical_key(i["gold_template"], i["gold_parameters"] or {})))
        if p.get("decision") == "accepted" and p.get("parameters") is not None and p.get("template") != "advisory":
            pred_keys.add((i["method"], c.canonical_key(p["template"], p["parameters"])))
    ktp = len(gold_keys & pred_keys)
    return {"n": len(items), "template_accuracy": correct / len(items), "executable": prf(tp, fp, fn),
            "key": prf(ktp, len(pred_keys) - ktp, len(gold_keys) - ktp),
            "review_queue": sum(1 for p in preds if p.get("decision") == "review"),
            "rejected_quote": sum(1 for p in preds if p.get("decision") == "rejected_quote")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--extractions", default=str(ROOT / "knowledge" / "method_extractions"))
    ap.add_argument("--llm", default=None)
    ap.add_argument("--arms", default="full,k1,retrieval_only,direct")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    c = load_canon()
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    slots, items = gold["slots"], gold["items"]
    llm = load_llm(args.llm) if args.llm else None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for arm in args.arms.split(","):
        if arm != "retrieval_only" and llm is None:
            raise SystemExit(f"--llm is required for arm {arm}")
        preds = []
        for item in items:
            text = sources(Path(args.extractions), item["method"]).get(item["source_id"], "")
            preds.append(predict(c, item, text, slots, arm, llm))
        (out / f"predictions_{arm}.json").write_text(json.dumps(preds, ensure_ascii=False, indent=1, default=str))
        summary[arm] = score(c, items, preds)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
