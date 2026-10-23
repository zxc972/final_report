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
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
import csv
import hashlib
import os
import threading
import time
import importlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "agent" / "modules" / "agent" / "backend"


def load_canon():
    spec = importlib.util.spec_from_file_location(
        "canon", BACKEND / "analysis_condition_canonicalizer.py"
    )
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
    st = {
        "statement": item["statement"],
        "quote": item["quote"],
        "source_id": item["source_id"],
    }
    if arm == "retrieval_only":
        top = c.Retriever().rank(item["statement"] + " " + item["quote"], k=1)[0][0]
        return {
            "decision": "advisory" if top == "advisory" else "accepted",
            "template": top,
            "parameters": None,
        }
    if arm == "direct":
        answer = c.parse_answer(
            llm(
                c.build_prompt(
                    item["statement"], item["quote"], list(c.TEMPLATES), slots
                )
            )
        )
        if answer is None:
            return {"decision": "advisory", "template": "advisory", "parameters": None}
        return {
            "decision": "accepted",
            "template": answer[0],
            "parameters": answer[1],
            "key": c.canonical_key(*answer),
            "source_id": item["source_id"],
            "statement": item["statement"],
        }
    samples = 1 if arm == "k1" else c.SAMPLES
    r = c.canonicalise_statement(st, source_text, slots, llm, samples=samples)
    if r["decision"] != "accepted":
        r["template"] = r.get("template") if r["decision"] == "review" else "advisory"
    return r


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {
        "precision": p,
        "recall": r,
        "f1": 2 * p * r / (p + r) if p + r else 0.0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def score(c, items, preds):
    correct = sum(
        1 for i, p in zip(items, preds) if p.get("template") == i["gold_template"]
    )
    exe = [
        (
            i["gold_template"] != "advisory",
            p.get("decision") == "accepted" and p.get("template") != "advisory",
        )
        for i, p in zip(items, preds)
    ]
    tp = sum(1 for g, q in exe if g and q)
    fp = sum(1 for g, q in exe if q and not g)
    fn = sum(1 for g, q in exe if g and not q)
    gold_keys, pred_keys = set(), set()
    for i, p in zip(items, preds):
        if i["gold_template"] != "advisory":
            gold_keys.add(
                (
                    i["method"],
                    c.canonical_key(i["gold_template"], i["gold_parameters"] or {}),
                )
            )
        if (
            p.get("decision") == "accepted"
            and p.get("parameters") is not None
            and p.get("template") != "advisory"
        ):
            pred_keys.add(
                (i["method"], c.canonical_key(p["template"], p["parameters"]))
            )
    ktp = len(gold_keys & pred_keys)
    return {
        "n": len(items),
        "template_accuracy": correct / len(items),
        "executable": prf(tp, fp, fn),
        "key": prf(ktp, len(pred_keys) - ktp, len(gold_keys) - ktp),
        "review_queue": sum(1 for p in preds if p.get("decision") == "review"),
        "rejected_quote": sum(
            1 for p in preds if p.get("decision") == "rejected_quote"
        ),
    }


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


@contextmanager
def run_lock(out):
    # Separate invocations must not race the shared request reservation ledger.
    with (out / "run.lock").open("a+b") as stream:
        try:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            import msvcrt

            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except BlockingIOError:
            raise SystemExit("Another evaluation process owns this output directory")
        yield


def preflight(
    c, gold_path, extractions, arms, llm_ref, public_config, workers, max_requests
):
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    items = gold["items"]
    ids = [i["id"] for i in items]
    if not items or len(ids) != len(set(ids)):
        raise ValueError("Gold items must have unique IDs and must not be empty")
    valid_arms = {"full", "k1", "retrieval_only", "direct"}
    if not arms or len(arms) != len(set(arms)) or not set(arms) <= valid_arms:
        raise ValueError("Unknown or duplicate arm")
    texts, hashes, quote_supports = {}, {}, {}
    for method in sorted({i["method"] for i in items}):
        path = extractions / f"{method}.input.json"
        texts[method] = sources(extractions, method)
        hashes[str(path.relative_to(extractions))] = sha256(path)
    for item in items:
        if item["source_id"] not in texts[item["method"]]:
            raise ValueError(f"Source ID missing for item {item['id']}")
        quote_supports[str(item["id"])] = c.quote_support(
            item["quote"], texts[item["method"]][item["source_id"]]
        )
    supported = sum(v >= c.RHO_MIN for v in quote_supports.values())
    expected = sum(
        (
            supported * c.SAMPLES
            if arm == "full"
            else supported if arm == "k1" else len(items) if arm == "direct" else 0
        )
        for arm in arms
    )
    if expected > max_requests:
        raise ValueError("Planned calls exceed the authorised total request budget")
    frozen = {
        "schema": "primatex.condition_canon_run.v1",
        "gold_status": gold.get("status"),
        "gold_sha256": sha256(gold_path),
        "source_sha256": hashes,
        "code_sha256": {
            "canonicalizer": sha256(BACKEND / "analysis_condition_canonicalizer.py"),
            "runner": sha256(Path(__file__)),
            "provider": sha256(Path(__file__).with_name("provider_llm.py")),
        },
        "parameters": {
            name: getattr(c, name)
            for name in ["RHO_MIN", "TOP_K", "SAMPLES", "LAMBDA", "TAU", "DELTA"]
        },
        "arms": arms,
        "llm": llm_ref,
        "provider": public_config,
        "workers": workers,
        "max_http_attempts": max_requests,
        "n_statements": len(items),
        "quote_supports": quote_supports,
        "expected_logical_calls": expected,
        "scoring": {
            "template": "best proposed template, including review; advisory when no proposal",
            "executable": "accepted and non-advisory; review/rejected/error are not executable",
            "key": "unique (method, canonical key) of accepted non-advisory parameterised predictions",
            "retrieval_only_keys": "no parameters, hence empty predicted key set",
        },
    }
    return gold, texts, frozen


def freeze_or_verify(out, frozen, resume):
    path = out / "frozen.json"
    if path.exists():
        if not resume:
            raise ValueError(
                "Output already has a frozen run; use --resume without changing inputs"
            )
        existing = json.loads(path.read_text(encoding="utf-8"))
        if {k: v for k, v in existing.items() if k != "frozen_at"} != frozen:
            raise ValueError(
                "Frozen inputs, code or configuration changed; refusing to resume"
            )
    else:
        if resume:
            raise ValueError("Cannot resume without a frozen run")
        save_json(path, {"frozen_at": datetime.now(timezone.utc).isoformat(), **frozen})
    digest = sha256(path)
    digest_path = out / "frozen.sha256"
    if digest_path.exists() and digest_path.read_text().strip() != digest:
        raise ValueError("Frozen manifest digest changed")
    digest_path.write_text(digest + "\n", encoding="utf-8")
    return digest


def score_with_details(c, items, preds):
    result = score(c, items, preds)
    positive = result["executable"]
    tn = len(items) - positive["tp"] - positive["fp"] - positive["fn"]
    result["advisory_or_not_executable"] = prf(tn, positive["fn"], positive["fp"])
    result["decisions"] = {
        decision: sum(p.get("decision") == decision for p in preds)
        for decision in [
            "accepted",
            "advisory",
            "review",
            "rejected_quote",
            "inference_error",
        ]
    }
    return result


def error_rows(c, items, preds):
    rows = []
    for item, pred in zip(items, preds):
        gold_executable = item["gold_template"] != "advisory"
        pred_executable = (
            pred.get("decision") == "accepted" and pred.get("template") != "advisory"
        )
        template_wrong = pred.get("template") != item["gold_template"]
        expected_key = (
            c.canonical_key(item["gold_template"], item["gold_parameters"] or {})
            if gold_executable
            else None
        )
        actual_key = (
            c.canonical_key(pred["template"], pred["parameters"])
            if pred_executable and pred.get("parameters") is not None
            else None
        )
        key_wrong = expected_key != actual_key
        if not (template_wrong or gold_executable != pred_executable or key_wrong):
            continue
        reasons = []
        if pred.get("decision") == "review":
            reasons.append(
                f"待审核：score={pred.get('score', 0):.4f}, margin={pred.get('margin', 0):.4f}, support={pred.get('support', 0):.2f}"
            )
        if pred.get("decision") == "rejected_quote":
            reasons.append("引文原文核对未达阈值")
        if pred.get("decision") == "inference_error":
            reasons.append("模型输出触发算法运行异常：" + pred["runtime_error_type"])
        if pred.get("decision") == "advisory":
            reasons.append(
                "没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支"
            )
        ranked = [x[0] for x in pred.get("candidates", [])]
        if template_wrong:
            reasons.append("模板标签与草稿标准不一致")
            if gold_executable and ranked and item["gold_template"] not in ranked:
                reasons.append("草稿标准模板不在检索 top-3 中")
        if gold_executable != pred_executable:
            reasons.append("可执行/非可执行判定与草稿标准不一致")
        if key_wrong and gold_executable and pred_executable:
            reasons.append("规范键参数与草稿标准不一致（未对同义表示额外修正）")
        rows.append(
            {
                "id": item["id"],
                "method": item["method"],
                "field": item["field"],
                "statement": item["statement"],
                "quote": item["quote"],
                "source_id": item["source_id"],
                "gold_template": item["gold_template"],
                "gold_parameters": item["gold_parameters"],
                "predicted_decision": pred.get("decision"),
                "predicted_template": pred.get("template"),
                "predicted_parameters": pred.get("parameters"),
                "template_wrong": template_wrong,
                "executable_wrong": gold_executable != pred_executable,
                "statement_key_wrong": key_wrong,
                "invalid_attempts": pred.get("invalid_attempts", {}),
                "reasons": reasons,
            }
        )
    return rows


def write_csv(path, rows):
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: (
                        json.dumps(v, ensure_ascii=False)
                        if isinstance(v, (dict, list))
                        else v
                    )
                    for k, v in row.items()
                }
            )


def write_reports(c, out, gold, all_preds, summary, provider, frozen_digest):
    items = gold["items"]
    rows = []
    for arm, metrics in summary.items():
        row = {
            "arm": arm,
            "n": metrics["n"],
            "template_accuracy": metrics["template_accuracy"],
        }
        for name in ["executable", "advisory_or_not_executable", "key"]:
            for measure in ["precision", "recall", "f1"]:
                row[name + "_" + measure] = metrics[name][measure]
        row.update(
            review_queue=metrics["review_queue"],
            rejected_quote=metrics["rejected_quote"],
        )
        row.update(metrics["usage"])
        row["observed_models"] = metrics["usage"].get("observed_models", [])
        rows.append(row)
    write_csv(out / "summary.csv", rows)
    errors = error_rows(c, items, all_preds.get("full", []))
    save_json(out / "full_errors.json", errors)
    write_csv(out / "full_errors.csv", errors)
    lines = [
        "# Full 组草稿标准错误清单",
        "",
        "标准答案尚未经用户审核；下列条目按模板、可执行判定或逐条规范键任一不一致列出。",
        "",
    ]
    for row in errors:
        lines += [
            f"## {row['id']} · {row['method']}",
            "",
            row["statement"],
            "",
            "草稿标准：`"
            + json.dumps(
                {
                    "template": row["gold_template"],
                    "parameters": row["gold_parameters"],
                },
                ensure_ascii=False,
            )
            + "`",
            "",
            "预测：`"
            + json.dumps(
                {
                    "decision": row["predicted_decision"],
                    "template": row["predicted_template"],
                    "parameters": row["predicted_parameters"],
                },
                ensure_ascii=False,
            )
            + "`",
            "",
            "原因：" + "；".join(row["reasons"]),
            "",
        ]
    (out / "full_errors.md").write_text("\n".join(lines), encoding="utf-8")
    total_usage = (
        provider.stats()
        if provider
        else {
            "logical_calls": 0,
            "http_attempts": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    )
    save_json(out / "usage.json", total_usage)
    save_json(
        out / "run_status.json",
        {
            "status": "completed",
            "label_status": gold.get("status"),
            "frozen_sha256": frozen_digest,
            "n_statements": len(items),
            "arms": list(summary),
            "full_error_items": len(errors),
            "usage": total_usage,
            "analysis_runs": 0,
            "preprocessing_submissions": 0,
            "formal_gold_created": False,
        },
    )
    lines = [
        "# 算法 1 草稿标注评测",
        "",
        "108 条草稿标签尚待用户审核。本结果不作为正式金标准评测；算法及默认阈值未调整。",
        "",
        "| 组别 | 模板准确率 | 可执行 P/R/F1 | 非可执行 P/R/F1 | 规范键 P/R/F1 | 审核队列 | 调用/HTTP请求 | token 输入/输出/合计 |",
        "|---|---:|---|---|---|---:|---|---|",
    ]
    fmt = lambda m: "/".join(f"{100*m[x]:.2f}%" for x in ["precision", "recall", "f1"])
    for arm, m in summary.items():
        u = m["usage"]
        lines.append(
            f"| {arm} | {100*m['template_accuracy']:.2f}% | {fmt(m['executable'])} | {fmt(m['advisory_or_not_executable'])} | {fmt(m['key'])} | {m['review_queue']} | {u['logical_calls']}/{u['http_attempts']} | {u['input_tokens']}/{u['output_tokens']}/{u['total_tokens']} |"
        )
    lines += [
        "",
        "模板准确率计入 review 的最佳提案；可执行正类仅为 accepted 且非 advisory。review、引文拒绝及运行错误按未接受计入二分类负类。",
        "",
        "retrieval_only 不产生参数，规范键预测集合为空，P/R/F1 按原评分器的零分约定报告。规范键按 (method, template, parameters) 去重计分。",
        "",
        f"full 组逐条错误 {len(errors)} 项，见 full_errors.md / full_errors.csv。引文、候选、分数和全部预测均已保存。",
        "",
        "每个模型响应及 token 记在 requests/calls.jsonl；失败及重试同样占用共享的 800 请求上限，未知 usage 不视为已知零 token。",
        "",
        f"冻结摘要：`{frozen_digest}`。正式标注冻结、正式重跑、敏感性分析及知识层新增/一致/冲突比较均等待用户审核通知。",
        "",
    ]
    (out / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--extractions", default=str(ROOT / "knowledge/method_extractions"))
    ap.add_argument("--llm", default=None)
    ap.add_argument("--arms", default="full,k1,retrieval_only,direct")
    ap.add_argument("--out", required=True)
    ap.add_argument("--provider-config")
    ap.add_argument("--model", default="deepseek-v4.1-flash")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-requests", type=int, default=800)
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    if not 1 <= args.workers <= 8:
        raise SystemExit("workers must be between 1 and 8")
    sys.path.insert(0, str(ROOT))
    from tools.knowledge import provider_llm

    c, arms = load_canon(), args.arms.split(",")
    llm = load_llm(args.llm) if args.llm else None
    if any(a != "retrieval_only" for a in arms) and llm is None:
        raise SystemExit("--llm is required for model arms")
    metered = args.llm == "tools.knowledge.provider_llm:complete"
    if llm and not metered:
        raise SystemExit("Scored model runs require the metered development adapter")
    config = (
        provider_llm.load_config(args.provider_config, model=args.model)
        if metered
        else None
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    gold, texts, frozen = preflight(
        c,
        Path(args.gold),
        Path(args.extractions),
        arms,
        args.llm,
        config.public() if config else None,
        args.workers,
        args.max_requests,
    )
    with run_lock(out):
        frozen_digest = freeze_or_verify(out, frozen, args.resume)
        if args.prepare_only:
            print(
                json.dumps(
                    {
                        "status": "frozen",
                        "expected_logical_calls": frozen["expected_logical_calls"],
                        "frozen_sha256": frozen_digest,
                    }
                )
            )
            return
        provider = (
            provider_llm.configure(
                config=config,
                ledger_dir=out / "requests",
                max_requests=args.max_requests,
            )
            if metered
            else None
        )
        all_preds, summary = {}, {}
        prior_summary = (
            json.loads((out / "summary.json").read_text())
            if (out / "summary.json").exists()
            else {}
        )
        try:
            for arm in arms:
                started, completed = time.monotonic(), 0
                preds = [None] * len(gold["items"])

                def one(index, item):
                    checkpoint = out / "checkpoints" / f"{arm}_{item['id']}.json"
                    if checkpoint.exists():
                        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
                        if (
                            saved["frozen_sha256"] != frozen_digest
                            or saved["item_id"] != item["id"]
                        ):
                            raise ValueError(
                                "Prediction checkpoint belongs to a different frozen run"
                            )
                        return index, saved["prediction"]
                    sample = 0

                    def call(prompt):
                        nonlocal sample
                        sample += 1
                        with provider_llm.scope(arm, item["id"], sample):
                            return llm(prompt)

                    try:
                        prediction = predict(
                            c,
                            item,
                            texts[item["method"]][item["source_id"]],
                            gold["slots"],
                            arm,
                            call,
                        )
                    except (TypeError, ValueError, KeyError, AttributeError) as error:
                        # Preserve algorithm failures as failures, never repair an answer or resample to improve a score.
                        prediction = {
                            "decision": "inference_error",
                            "template": None,
                            "parameters": None,
                            "runtime_error_type": type(error).__name__,
                            "sample_calls": sample,
                        }
                    prediction = {
                        "id": item["id"],
                        "method": item["method"],
                        **prediction,
                    }
                    save_json(
                        checkpoint,
                        {
                            "item_id": item["id"],
                            "frozen_sha256": frozen_digest,
                            "prediction": prediction,
                        },
                    )
                    return index, prediction

                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futures = [
                        pool.submit(one, index, item)
                        for index, item in enumerate(gold["items"])
                    ]
                    for future in as_completed(futures):
                        index, prediction = future.result()
                        preds[index] = prediction
                        completed += 1
                        if completed % 10 == 0 or completed == len(preds):
                            print(
                                f"{arm}: {completed}/{len(preds)} statements complete",
                                flush=True,
                            )
                all_preds[arm] = preds
                save_json(out / f"predictions_{arm}.json", preds)
                save_json(
                    out / f"review_queue_{arm}.json",
                    [
                        {"item": item, "prediction": pred}
                        for item, pred in zip(gold["items"], preds)
                        if pred["decision"] == "review"
                    ],
                )
                merged = []
                for method in sorted({i["method"] for i in gold["items"]}):
                    merged += c.merge(
                        [
                            p
                            for p in preds
                            if p["method"] == method and p.get("parameters") is not None
                        ],
                        method,
                    )
                save_json(out / f"merged_{arm}.json", merged)
                metrics = score_with_details(c, gold["items"], preds)
                metrics["elapsed_seconds"] = prior_summary.get(arm, {}).get(
                    "elapsed_seconds", round(time.monotonic() - started, 3)
                )
                metrics["usage"] = (
                    provider.stats(arm)
                    if provider
                    else {
                        "logical_calls": 0,
                        "http_attempts": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                    }
                )
                summary[arm] = metrics
                save_json(out / "summary.json", summary)
            write_reports(c, out, gold, all_preds, summary, provider, frozen_digest)
            print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        except BaseException as error:
            save_json(
                out / "run_status.json",
                {
                    "status": "interrupted",
                    "error_type": type(error).__name__,
                    "frozen_sha256": frozen_digest,
                    "usage": provider.stats() if provider else {},
                    "instruction": "Keep code, data and model unchanged; resume uses cached successful calls",
                },
            )
            raise
        finally:
            if provider:
                provider.close()


if __name__ == "__main__":
    main()
