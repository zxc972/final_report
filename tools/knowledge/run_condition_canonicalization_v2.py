"""Round 17 development evaluation; independent cards are never evaluated here.

The reviewed 108 statements are a development set. V1 is rescored from saved
predictions only. Scoring semantics remain those of the original runner.
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

ARMS = ("full_v2", "k1_v2", "direct_v2")
PENDING = {
    5: "advisory",
    13: "advisory",
    41: "software",
    42: "advisory",
    76: "advisory",
    102: "advisory",
}
DEV_CAP = 1188
EXTRACTION_CAP = 12


def load_vocab(root=ROOT):
    folder = root / "agent/modules/agent/knowledge_analysis"
    files = [folder / "product_types.json", folder / "workflow_steps.json"]
    types, steps = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    return {
        "types": sorted({t["id"] for t in types["types"]}),
        "steps": sorted({s["id"] for s in steps["steps"]} | {"recon-all"}),
    }, {p.name: base.sha256(p) for p in files}


def prompt_for(c, item, slots, vocab, direct=False):
    # Whitelist input fields; gold and review notes never enter a prompt.
    prompt = c.build_prompt_v2(
        item["statement"], item["quote"], item["field"], slots, {} if direct else vocab
    )
    if direct:
        prompt = prompt.replace("Allowed product types: []\n", "")
        prompt = prompt.replace("Allowed processing steps: []\n", "")
    return prompt


def predict(c, item, source_text, slots, vocab, arm, llm):
    if arm == "direct_v2":
        answer = c.parse_answer(llm(prompt_for(c, item, slots, vocab, direct=True)))
        if answer is None or answer[0] == "advisory":
            return {"decision": "advisory", "template": "advisory", "parameters": None}
        # Deliberately no vocabulary, normalisation, type checking or voting.
        return {
            "decision": "accepted",
            "template": answer[0],
            "parameters": answer[1],
            "key": c.canonical_key(*answer),
        }
    if arm not in ARMS:
        raise ValueError("Unknown v2 arm")
    st = {k: item[k] for k in ["statement", "quote", "source_id"]}
    return c.canonicalise_statement_v2(
        st,
        source_text,
        slots,
        llm,
        vocab,
        field=item["field"],
        samples=5 if arm == "full_v2" else 1,
    )


class SampleCaller:
    """Replace at most ONE length-limited sample per (arm, statement).

    The original response remains in the ledger. Replacement uses an identical
    prompt/config, a distinct cached scope, and the same one vote position.
    A second truncation is retained without another replacement.
    """

    def __init__(self, provider, arm, item_id):
        self.provider, self.arm, self.item_id = provider, arm, item_id
        self.nominal, self.replacements, self.records = 0, 0, []

    def receive(self, prompt, sample, replacement_of=None):
        with transport.scope(self.arm, self.item_id, sample):
            text = self.provider.complete(prompt)
        meta = self.provider.response_info(self.arm, self.item_id, sample)
        self.records.append(
            {"sample": sample, "replacement_of": replacement_of, **meta}
        )
        return text, meta

    def __call__(self, prompt):
        self.nominal += 1
        text, meta = self.receive(prompt, self.nominal)
        if meta.get("finish_reason") == "length" and self.replacements == 0:
            self.replacements += 1
            text, _ = self.receive(
                prompt, f"length_replacement_{self.nominal}", self.nominal
            )
        return text

    def public(self):
        return {
            "nominal_samples": self.nominal,
            "truncation_replacements": self.replacements,
            "responses": self.records,
        }


def freeze_inputs(c, args, config):
    gold_path, extractions = Path(args.gold), Path(args.extractions)
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    items = gold["items"]
    assert len(items) == 108 and len({i["id"] for i in items}) == 108
    by_id = {i["id"]: i for i in items}
    for i, label in PENDING.items():
        assert by_id[i]["gold_template"] == label
    vocab, vocab_hashes = load_vocab()
    texts, source_hashes, quotes = {}, {}, {}
    for method in sorted({i["method"] for i in items}):
        texts[method] = base.sources(extractions, method)
        source_hashes[method + ".input.json"] = base.sha256(
            extractions / (method + ".input.json")
        )
    for i in items:
        quotes[str(i["id"])] = c.quote_support(
            i["quote"], texts[i["method"]][i["source_id"]]
        )
    code = [
        base.BACKEND / "analysis_condition_canonicalizer.py",
        Path(__file__),
        Path(transport.__file__),
        Path(base.__file__),
    ]
    v1 = {
        a: base.sha256(Path(args.v1_dir) / f"predictions_{a}.json")
        for a in ["full", "k1", "retrieval_only", "direct"]
    }
    frozen = {
        "schema": "primatex.condition_canon_run.v2",
        "split": "development",
        "gold_sha256": base.sha256(gold_path),
        "gold_status": gold["status"],
        "temporary_pending_decisions": PENDING,
        "source_sha256": source_hashes,
        "vocabulary_sha256": vocab_hashes,
        "vocabulary": vocab,
        "v1_prediction_sha256": v1,
        "code_sha256": {str(p.relative_to(ROOT)): base.sha256(p) for p in code},
        "parameters": {
            n: getattr(c, n) for n in ["RHO_MIN", "SAMPLES", "V2_SUPPORT", "V2_MARGIN"]
        },
        "arms": list(ARMS),
        "provider": config.public(),
        "workers": args.workers,
        "transport_pacing": {
            "minimum_seconds": 2.0,
            "429_multiplier": 1.25,
            "maximum_seconds": 6.0,
            "reduce_after_successes": 32,
            "reduction": 0.9,
        },
        "budget": {
            "user_total_http_cap": 1200,
            "development_http_cap": args.max_requests,
            "independent_extraction_http_cap": EXTRACTION_CAP,
        },
        "base_sample_positions": 108 * 7,
        "maximum_truncation_replacements": 108 * 3,
        "truncation_policy": "one replacement per arm/statement; identical prompt/settings; original retained; one vote position",
        "direct_v2_policy": "v2 definitions and field; no allowed-vocabulary lines, normalisation, type check or vote",
        "quote_supports": quotes,
        "scoring": "v1 scorer unchanged; template uses best proposal including review; executable requires accepted/non-advisory; keys deduplicate method/key",
        "independent_test_evaluation": False,
    }
    # JSON round-trip keeps numeric item keys consistent on resume.
    return gold, texts, vocab, json.loads(json.dumps(frozen))


def rescore_v1(c, gold, folder, out):
    summary = {}
    for arm in ["full", "k1", "retrieval_only", "direct"]:
        path = folder / f"predictions_{arm}.json"
        preds = json.loads(path.read_text(encoding="utf-8"))
        assert [p["id"] for p in preds] == [i["id"] for i in gold["items"]]
        metrics = base.score_with_details(c, gold["items"], preds)
        metrics.update(new_model_calls=0, prediction_sha256=base.sha256(path))
        summary["v1_" + arm] = metrics
    base.save_json(out / "v1_rescored.json", summary)
    return summary


def error_rows(c, items, preds):
    rows = base.error_rows(c, items, preds)
    by_id = {p["id"]: p for p in preds}
    for row in rows:
        p = by_id[row["id"]]
        reasons = []
        if p["decision"] in {"provider_error", "inference_error"}:
            reasons.append("运行/接口失败，单列环境或输出结构问题")
        if p["decision"] == "review":
            reasons.append(
                f"未接受：support={p.get('support')}, margin={p.get('margin')}, answered={p.get('answered')}"
            )
        if row["template_wrong"]:
            reasons.append("主模板与审核版开发集标准不一致")
        if row["executable_wrong"]:
            reasons.append("可执行/非可执行判定不一致")
        if row["statement_key_wrong"]:
            reasons.append("逐条规范键不一致（严格字符串，不增设同义规则）")
        row.update(
            reasons=reasons, votes=p.get("votes", {}), sampling=p.get("sampling", {})
        )
    return rows


def reports(c, out, gold, summaries, predictions, provider, frozen_sha):
    rows = []
    for arm, m in summaries.items():
        row = {"arm": arm, "n": m["n"], "template_accuracy": m["template_accuracy"]}
        for metric in ["executable", "advisory_or_not_executable", "key"]:
            for measure in ["precision", "recall", "f1"]:
                row[metric + "_" + measure] = m[metric][measure]
        u = m.get("usage", {})
        row.update(
            review_queue=m["review_queue"],
            logical_calls=u.get("logical_calls", 0),
            http_attempts=u.get("http_attempts", 0),
            input_tokens=u.get("input_tokens", 0),
            output_tokens=u.get("output_tokens", 0),
            total_tokens=u.get("total_tokens", 0),
            length_responses=u.get("length_limited_responses", 0),
            truncation_replacements=m.get("truncation_replacements", 0),
        )
        rows.append(row)
    base.write_csv(out / "summary.csv", rows)
    base.save_json(out / "summary.json", summaries)
    errors = error_rows(c, gold["items"], predictions["full_v2"])
    base.save_json(out / "full_v2_errors.json", errors)
    base.write_csv(out / "full_v2_errors.csv", errors)
    lines = [
        "# full_v2 开发集错误清单",
        "",
        "逐条列出模板、执行判定或严格规范键不一致；不据此调参。",
        "",
    ]
    for row in errors:
        lines += [
            f"## {row['id']} · {row['method']}",
            "",
            row["statement"],
            "",
            "原文引用：" + row["quote"],
            "",
            "审核版标准："
            + json.dumps(
                {
                    "template": row["gold_template"],
                    "parameters": row["gold_parameters"],
                },
                ensure_ascii=False,
            ),
            "",
            "预测："
            + json.dumps(
                {
                    "decision": row["predicted_decision"],
                    "template": row["predicted_template"],
                    "parameters": row["predicted_parameters"],
                },
                ensure_ascii=False,
            ),
            "",
            "原因：" + "；".join(row["reasons"]),
            "",
            "票数：" + json.dumps(row["votes"], ensure_ascii=False),
            "",
        ]
    (out / "FULL_V2_ERRORS.md").write_text("\n".join(lines), encoding="utf-8")
    ends = {e["request_id"]: e for e in provider.events if e["event"] == "end"}
    usage_rows = []
    for e in provider.events:
        if e["event"] != "start":
            continue
        end = ends.get(e["request_id"], {})
        usage_rows.append(
            {
                k: (e if k in e else end).get(k)
                for k in [
                    "ordinal",
                    "arm",
                    "item_id",
                    "sample",
                    "attempt",
                    "request_id",
                    "status",
                    "http_status",
                    "finish_reason",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "reasoning_content_present",
                    "reasoning_tokens",
                ]
            }
        )
    base.write_csv(out / "call_usage.csv", usage_rows)
    usage = provider.stats()
    base.save_json(out / "usage.json", usage)
    base.save_json(
        out / "run_status.json",
        {
            "status": "completed",
            "split": "development",
            "n": 108,
            "frozen_sha256": frozen_sha,
            "full_v2_error_items": len(errors),
            "usage": usage,
            "independent_test_evaluation_calls": 0,
            "analysis_runs": 0,
            "preprocessing_submissions": 0,
        },
    )
    fmt = lambda m: "/".join(f"{100*m[k]:.2f}" for k in ["precision", "recall", "f1"])
    lines = [
        "# 第十七轮：条件规范化开发集",
        "",
        "108 条是开发集，不能作为独立正式测试集。6 条待决定暂按用户指定的 Claude 建议计分，未改变审核状态。",
        "",
        "| 组别 | 模板准确率 % | 可执行 P/R/F1 % | 非可执行 P/R/F1 % | 规范键 P/R/F1 % | 审核队列 | 新 HTTP | 已知 token |",
        "|---|---:|---|---|---|---:|---:|---:|",
    ]
    for arm, m in summaries.items():
        u = m.get("usage", {})
        lines.append(
            f"| {arm} | {100*m['template_accuracy']:.2f} | {fmt(m['executable'])} | {fmt(m['advisory_or_not_executable'])} | {fmt(m['key'])} | {m['review_queue']} | {u.get('http_attempts',0)} | {u.get('total_tokens',0)} |"
        )
    lines += [
        "",
        "v1 四组只更换标准答案重算，历史预测文件摘要已冻结，没有新调用。retrieval_only 不填参数，规范键按原评分器空集合零分约定报告。",
        "",
        "v2 模型设置：" + json.dumps(provider.config.public(), ensure_ascii=False),
        "",
        "使用量：" + json.dumps(usage, ensure_ascii=False),
        "",
        "截断补采："
        + json.dumps(
            {a: summaries[a]["truncation_replacements"] for a in ARMS},
            ensure_ascii=False,
        ),
        "",
        f"full_v2 错误 {len(errors)} 条，见 FULL_V2_ERRORS.md。冻结 SHA：{frozen_sha}",
        "",
    ]
    (out / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--gold", default=str(ROOT / "evaluation/condition_gold/gold_reviewed_v1.json")
    )
    ap.add_argument("--extractions", default=str(ROOT / "knowledge/method_extractions"))
    ap.add_argument("--v1-dir", default=str(ROOT / "results/condition_canon_draft_v1"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--provider-config", required=True)
    ap.add_argument("--model", default="deepseek-v4.1-flash")
    ap.add_argument("--max-requests", type=int, default=DEV_CAP)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    assert 1 <= args.max_requests <= DEV_CAP and 1 <= args.workers <= 4
    config = transport.load_config(
        args.provider_config,
        model=args.model,
        temperature=0.7,
        max_tokens=8192,
        thinking="disabled",
        json_output=True,
        timeout=180,
    )
    c = base.load_canon()
    gold, texts, vocab, frozen = freeze_inputs(c, args, config)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with base.run_lock(out):
        digest = base.freeze_or_verify(out, frozen, args.resume)
        summary = rescore_v1(c, gold, Path(args.v1_dir), out)
        if args.prepare_only:
            print(
                json.dumps(
                    {
                        "status": "frozen",
                        "frozen_sha256": digest,
                        "base_samples": frozen["base_sample_positions"],
                        "provider": config.public(),
                    }
                ),
                flush=True,
            )
            return
        provider = transport.Provider(
            config, out / "requests", args.max_requests, minimum_interval=2.0
        )
        predictions = {}
        try:
            for arm in ARMS:
                started = time.monotonic()

                def one(index, item):
                    path = out / "checkpoints" / f"{arm}_{item['id']}.json"
                    if path.exists():
                        checkpoint = json.loads(path.read_text(encoding="utf-8"))
                        assert checkpoint["frozen_sha256"] == digest
                        return index, checkpoint["prediction"]
                    caller = SampleCaller(provider, arm, item["id"])
                    try:
                        p = predict(
                            c,
                            item,
                            texts[item["method"]][item["source_id"]],
                            gold["slots"],
                            vocab,
                            arm,
                            caller,
                        )
                    except transport.ProviderFailure as error:
                        if any(f"HTTP {s}" in str(error) for s in [400, 401, 403, 422]):
                            raise
                        p = {
                            "decision": "provider_error",
                            "template": None,
                            "parameters": None,
                            "error_summary": str(error),
                        }
                    except (TypeError, ValueError, KeyError, AttributeError) as error:
                        p = {
                            "decision": "inference_error",
                            "template": None,
                            "parameters": None,
                            "runtime_error_type": type(error).__name__,
                        }
                    p = {
                        "id": item["id"],
                        "method": item["method"],
                        **p,
                        "sampling": caller.public(),
                    }
                    base.save_json(path, {"frozen_sha256": digest, "prediction": p})
                    return index, p

                preds = [None] * len(gold["items"])
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futures = [
                        pool.submit(one, index, item)
                        for index, item in enumerate(gold["items"])
                    ]
                    for done, future in enumerate(as_completed(futures), 1):
                        try:
                            index, p = future.result()
                        except BaseException:
                            for f in futures:
                                f.cancel()
                            raise
                        preds[index] = p
                        if done % 10 == 0 or done == 108:
                            print(
                                f"{arm}: {done}/108; HTTP={provider.stats()['http_attempts']}",
                                flush=True,
                            )
                predictions[arm] = preds
                base.save_json(out / f"predictions_{arm}.json", preds)
                base.save_json(
                    out / f"review_queue_{arm}.json",
                    [
                        {"item": i, "prediction": p}
                        for i, p in zip(gold["items"], preds)
                        if p["decision"] == "review"
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
                base.save_json(out / f"merged_{arm}.json", merged)
                m = base.score_with_details(c, gold["items"], preds)
                m.update(
                    usage=provider.stats(arm),
                    elapsed_seconds=round(time.monotonic() - started, 3),
                    truncation_replacements=sum(
                        p["sampling"]["truncation_replacements"] for p in preds
                    ),
                )
                summary[arm] = m
                base.save_json(out / "summary.json", summary)
            reports(c, out, gold, summary, predictions, provider, digest)
            print(
                json.dumps({"status": "completed", "usage": provider.stats()}),
                flush=True,
            )
        finally:
            provider.close()


if __name__ == "__main__":
    main()
