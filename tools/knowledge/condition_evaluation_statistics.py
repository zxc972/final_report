"""Preregistered Round18 scoring, statement bootstrap, and exact paired tests."""
from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import random

from tools.knowledge import run_condition_canonicalization as base

METRICS = ["template_accuracy"] + [f"{kind}.{stat}" for kind in
    ["executable", "advisory_or_not_executable", "key"] for stat in ["precision", "recall", "f1"]] + ["review_queue"]


def flatten(metrics):
    result = {}
    for name in METRICS:
        value = metrics
        for key in name.split("."):
            value = value[key]
        result[name] = value
    return result


def percentile(values, fraction):
    ordered = sorted(values)
    location = fraction * (len(ordered) - 1)
    low = math.floor(location)
    high = math.ceil(location)
    return ordered[low] + (ordered[high] - ordered[low]) * (location - low)


def bootstrap(c, items, predictions, replicates=2000, seed=20261023):
    """Paired statement draws; original deduplicated method/key scorer is retained.

    Repeated statements contribute multiplicity to row metrics and queue counts.
    Canonical keys remain SETS within methods, including in each resample.
    """
    assert items and replicates >= 2
    assert all([p["id"] for p in preds] == [i["id"] for i in items] for preds in predictions.values())
    point = {arm: base.score_with_details(c, items, preds) for arm, preds in predictions.items()}
    draws = {arm: {key: [] for key in METRICS} for arm in predictions}
    rng = random.Random(seed)
    for _ in range(replicates):
        indices = rng.choices(range(len(items)), k=len(items))
        sample = [items[j] for j in indices]
        for arm, preds in predictions.items():
            values = flatten(base.score_with_details(c, sample, [preds[j] for j in indices]))
            for name, value in values.items():
                draws[arm][name].append(value)
    result = {}
    for arm in predictions:
        result[arm] = {"metrics": point[arm], "intervals_95": {
            name: {"estimate": flatten(point[arm])[name], "low": percentile(values, .025),
                   "high": percentile(values, .975)} for name, values in draws[arm].items()}}
    return {"n": len(items), "replicates": replicates, "seed": seed,
            "interval_method": "paired statement percentile bootstrap, linear quantiles",
            "key_set_policy": "unique (method,key) sets recomputed in each resample; repeated rows collapse in key sets",
            "arms": result}


def statement_key_correct(c, item, pred):
    # Exactly the existing error_rows expected/actual key convention, including None.
    expected = c.canonical_key(item["gold_template"], item.get("gold_parameters") or {}) if item["gold_template"] != "advisory" else None
    actual = c.canonical_key(pred["template"], pred["parameters"]) if (
        pred.get("decision") == "accepted" and pred.get("template") != "advisory"
        and pred.get("parameters") is not None) else None
    return expected == actual


def exact_mcnemar(first, second):
    assert len(first) == len(second)
    both = sum(a and b for a, b in zip(first, second))
    first_only = sum(a and not b for a, b in zip(first, second))
    second_only = sum(b and not a for a, b in zip(first, second))
    neither = sum(not a and not b for a, b in zip(first, second))
    discordant = first_only + second_only
    tail = sum(math.comb(discordant, k) for k in range(min(first_only, second_only) + 1))
    p = min(1.0, 2 * tail / (2 ** discordant)) if discordant else 1.0
    return {"n": len(first), "both_correct": both, "first_only_correct": first_only,
            "second_only_correct": second_only, "neither_correct": neither,
            "discordant": discordant, "p_exact_two_sided": p,
            "method": "exact binomial McNemar, unadjusted", "first_correct": both + first_only,
            "second_correct": both + second_only}


def paired_comparisons(c, items, predictions):
    correctness = {a: [statement_key_correct(c, i, p) for i, p in zip(items, preds)]
                   for a, preds in predictions.items()}
    return {f"{arm}_vs_direct_v2": exact_mcnemar(correctness[arm], correctness["direct_v2"])
            for arm in ["full_v2", "k1_v2"]}


def full_errors(c, items, preds):
    errors = base.error_rows(c, items, preds)
    by_id = {p["id"]: p for p in preds}
    pending = {i["id"] for i in items if i.get("pending_user_decision")}
    for row in errors:
        p = by_id[row["id"]]
        reasons = []
        if p.get("sampling", {}).get("unavailable_positions"):
            reasons.append("接口样本仍缺失；K 分母保持不变，缺失位置不产生票")
        if p["decision"] == "review":
            reasons.append(f"进入审核队列：support={p.get('support')}, margin={p.get('margin')}, answered={p.get('answered')}")
        if p.get("reason"):
            reasons.append(str(p["reason"]))
        if row["template_wrong"]:
            reasons.append("主模板与冻结标准不一致")
        if row["executable_wrong"]:
            reasons.append("可执行/非可执行判定与冻结标准不一致")
        if row["statement_key_wrong"]:
            reasons.append("逐条严格规范键不一致；保留原字符串，不增加同义规则")
        if p.get("invalid_attempts"):
            reasons.append("类型/词表检查排除了部分样本：" + json.dumps(p["invalid_attempts"], ensure_ascii=False))
        row.update(reasons=reasons, votes=p.get("votes", {}), pending_user_decision=row["id"] in pending,
                   support=p.get("support"), margin=p.get("margin"), sampling=p.get("sampling", {}))
    return errors


def point_table(report):
    fmt = lambda m: "/".join(f"{100*m[k]:.2f}" for k in ["precision", "recall", "f1"])
    rows = ["| 组别 | 模板准确率 % | 可执行 P/R/F1 % | 非可执行 P/R/F1 % | 规范键 P/R/F1 % | 审核条数 |",
            "|---|---:|---|---|---|---:|"]
    for arm, result in report["arms"].items():
        m = result["metrics"]
        rows.append(f"| {arm} | {100*m['template_accuracy']:.2f} | {fmt(m['executable'])} | {fmt(m['advisory_or_not_executable'])} | {fmt(m['key'])} | {m['review_queue']} |")
    return rows


def ci_table(report):
    arms = list(report["arms"])
    rows = ["| 指标：点估计 [95% CI]，除审核数外均为 % | " + " | ".join(arms) + " |",
            "|---|" + "---:|" * len(arms)]
    for metric in METRICS:
        values = []
        scale = 1 if metric == "review_queue" else 100
        for arm in arms:
            ci = report["arms"][arm]["intervals_95"][metric]
            values.append(f"{scale*ci['estimate']:.2f} [{scale*ci['low']:.2f}, {scale*ci['high']:.2f}]")
        rows.append("| " + metric + " | " + " | ".join(values) + " |")
    return rows


def write_reports(c, out, gold, dev, predictions, previous, provider, frozen_sha):
    out = Path(out)
    formal = {arm: predictions[arm] for arm in ["full_v2", "k1_v2", "direct_v2", "retrieval_only"]}
    primary = bootstrap(c, gold["items"], formal)
    indices = [j for j, item in enumerate(gold["items"]) if not item["pending_user_decision"]]
    subset = [gold["items"][j] for j in indices]
    reduced = {arm: [preds[j] for j in indices] for arm, preds in formal.items()}
    sensitivity = bootstrap(c, subset, reduced)
    paired = {"all_45": paired_comparisons(c, gold["items"], formal),
              "nonpending_39": paired_comparisons(c, subset, reduced)}
    base.save_json(out / "metrics_45.json", primary)
    base.save_json(out / "metrics_39.json", sensitivity)
    base.save_json(out / "mcnemar.json", paired)
    metric_rows = []
    for split, report in [("all_45", primary), ("nonpending_39", sensitivity)]:
        for arm, result in report["arms"].items():
            for name, ci in result["intervals_95"].items():
                metric_rows.append({"split": split, "n": report["n"], "arm": arm, "metric": name, **ci})
    base.write_csv(out / "metrics_with_ci.csv", metric_rows)
    correctness = [{"id": i["id"], "pending_user_decision": i["pending_user_decision"],
                    **{arm: statement_key_correct(c, i, formal[arm][j]) for arm in formal}}
                   for j, i in enumerate(gold["items"])]
    base.write_csv(out / "paired_key_correctness.csv", correctness)
    errors = full_errors(c, gold["items"], formal["full_v2"])
    base.save_json(out / "full_v2_errors.json", errors)
    base.write_csv(out / "full_v2_errors.csv", errors)
    lines = ["# full_v2 独立测试集错误清单", "", "按模板、执行判定或逐条严格规范键任一不一致列出；未据此调参。", ""]
    for e in errors:
        lines += [f"## {e['id']} · {e['method']}" + ("（待用户决定项）" if e["pending_user_decision"] else ""), "",
                  e["statement"], "", "引文：" + e["quote"], "",
                  "冻结标准：" + json.dumps({"template": e["gold_template"], "parameters": e["gold_parameters"]}, ensure_ascii=False), "",
                  "预测：" + json.dumps({"decision": e["predicted_decision"], "template": e["predicted_template"], "parameters": e["predicted_parameters"]}, ensure_ascii=False), "",
                  "原因：" + "；".join(e["reasons"]), "", "票数：" + json.dumps(e["votes"], ensure_ascii=False), ""]
    (out / "FULL_V2_ERRORS.md").write_text("\n".join(lines), encoding="utf-8")
    old = base.score_with_details(c, dev["items"], previous)
    repaired = predictions["dev_full_v2_repair"]
    new = base.score_with_details(c, dev["items"], repaired)
    changed_ids = [a["id"] for a, b in zip(previous, repaired) if a != b]
    assert changed_ids == [1, 2, 6, 11, 14, 15, 16, 19]
    development = {"n": 108, "before": old, "after": new, "updated_statement_ids": changed_ids,
                   "unchanged_statement_count": 100, "new_usage": provider.stats("dev_full_v2_repair"),
                   "historical_successful_samples_reused_in_repaired_statements": sum(r.get("historical", False) for p in repaired if p["id"] in changed_ids for r in p["sampling"]["responses"])}
    base.save_json(out / "development_repair.json", development)
    base.save_json(out / "development_full_v2_errors.json", full_errors(c, dev["items"], repaired))
    summaries = {a: provider.stats(a) for a in [*formal, "dev_full_v2_repair"]}
    totals = provider.stats()
    supplemental = {a: {"interface_replacements": sum(p.get("sampling", {}).get("interface_replacements", 0) for p in predictions[a]),
                         "truncation_replacements": sum(p.get("sampling", {}).get("truncation_replacements", 0) for p in predictions[a]),
                         "unavailable_positions": sum(len(p.get("sampling", {}).get("unavailable_positions", [])) for p in predictions[a])} for a in summaries}
    responses = [e for e in provider.events if e["event"] == "end" and e.get("status") == "ok"]
    strict = 0
    for e in responses:
        try:
            strict += isinstance(json.loads(e["text"]), dict)
        except (TypeError, json.JSONDecodeError):
            pass
    settings_audit = {"requested": provider.config.public(), "observed_models": totals["observed_models"],
                      "reasoning_content_present": sum(bool(e.get("reasoning_content_present")) for e in responses),
                      "reasoning_tokens_positive": sum((e.get("reasoning_tokens") or 0) > 0 for e in responses),
                      "successful_responses": len(responses), "strict_json_objects": strict,
                      "non_strict_json_objects": len(responses) - strict,
                      "failure_http_status_counts": dict(Counter(str(e.get("http_status")) for e in provider.events if e["event"] == "end" and e.get("status") != "ok"))}
    base.save_json(out / "usage_by_arm.json", summaries)
    base.save_json(out / "supplemental_samples.json", supplemental)
    base.save_json(out / "provider_settings_audit.json", settings_audit)
    md = ["# 第十八轮：冻结独立测试集正式评测", "",
          "45 条由 Claude 盲标；冻结前逐条核验 ID、原陈述字段、引文跨度及交接包全部 13 个文件摘要。标准答案原字节保留。", "",
          "Gold SHA-256：`e34d6796259e87f44f3bcede9c304eb87b4c1a5e31605cdfd357085bdac45135`。", "",
          "冻结时间（UTC）：" + json.loads((out / "frozen.json").read_text())["gold_freeze"]["frozen_at_utc"] + "；运行协议 SHA：`" + frozen_sha + "`。", "",
          "6 条 pending（1003、1004、1017、1019、1023、1041）保留文件标注计分；其余 39 条另报敏感性结果。", "",
          "## 45 条主结果", "", *point_table(primary), "", *ci_table(primary), "",
          "## 排除 6 条待决定项：39 条", "", *point_table(sensitivity), "", *ci_table(sensitivity), "",
          "## 配对比较", "",
          "逐条比较期望键与已接受且有参数的预测键；建议性标准的键为 None，未接受或无参数预测的键也为 None，沿用原 error_rows 口径。因此本二元指标包含非可执行陈述的无键一致，不等同于汇总去重后的规范键 P/R/F1。", "",
          "| 样本 | 比较 | 仅前者正确 b | 仅 direct 正确 c | 双方正确 | 双方错误 | 双侧精确 p（未校正） |",
          "|---|---|---:|---:|---:|---:|---:|"]
    for split, comparisons in paired.items():
        for name, m in comparisons.items():
            md.append(f"| {split} | {name} | {m['first_only_correct']} | {m['second_only_correct']} | {m['both_correct']} | {m['neither_correct']} | {m['p_exact_two_sided']:.8g} |")
    md += ["", "## 统计口径", "",
           "按陈述配对 bootstrap 2000 次，固定种子 20261023，线性插值的 2.5%/97.5% 分位区间。每次抽取与当前集合相同数量的陈述，组间使用同一抽样索引。模板及分类指标按抽取行计数；规范键沿用第十七轮评分器，在每次抽样内按 (method,key) 集合去重；审核队列区间是重采样审核条数的区间。零分母按原约定给 0。模板准确率使用最佳提议（包括 review），可执行要求 accepted 且非 advisory。非可执行包含 review 与接口失败。两项预先指定 McNemar 比较报告未校正精确双侧 p；小样本区间应结合计数阅读。", "",
           "## 调用与接口", "",
           "| 组别 | 逻辑调用 | HTTP（含重试） | 输入 token | 输出 token | 已知总 token | 用量未知请求 | 接口补采 | 截断补采 | 缺失槽位 |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for arm, u in summaries.items():
        s = supplemental[arm]
        md.append(f"| {arm} | {u['logical_calls']} | {u['http_attempts']} | {u['input_tokens']} | {u['output_tokens']} | {u['total_tokens']} | {u['unknown_usage_requests']} | {s['interface_replacements']} | {s['truncation_replacements']} | {s['unavailable_positions']} |")
    md += ["", "总调用统计：" + json.dumps(totals, ensure_ascii=False), "",
           "实际设置与响应核验：" + json.dumps(settings_audit, ensure_ascii=False), "",
           "每个接口失败的逻辑采样耗尽原适配器最多 3 次 HTTP 后，每组每陈述最多补 1 个样本；仍失败的位置不产生票，后续位置继续，K 分母不变。截断沿用上一轮每组每陈述最多补 1 个样本，保留原回答。已收到的空回答、错误参数、非严格 JSON 均不因语义问题补跑。所有请求与重试计入同一个 600 次上限。接口失败条目及恢复情况见 interface_failures.json，逐请求 token 见 call_usage.csv；失败请求用量未知不记为零。", "",
           "## 开发集补充", "",
           "仅更新 1、2、6、11、14、15、16、19；保留原轮文件，100 条其他预测逐条不变。原 8 个接口失败槽位和因提前终止尚未启动的 16 个槽位，共补 24 个位置；这些陈述内已收到的 16 个样本逐字复用，不重新采样。", "",
           *point_table({"arms": {"full_v2_before": {"metrics": old}, "full_v2_after": {"metrics": new}}}), "",
           "开发集 6 条待决定仍按第十七轮暂定标注处理；开发集仍是开发集，不混入独立测试集。详见 development_repair.json 与 predictions_dev_full_v2_repair.json。", "",
           "## 错误与约束确认", "", f"full_v2 共 {len(errors)} 条模板、执行判定或逐条规范键错误；逐项陈述、冻结标准、预测、原因、票数见 FULL_V2_ERRORS.md。算法文件、阈值、提示、vocab 和 slots 均与第十七轮一致，没有根据测试结果调参。", "",
           "未输出密钥；未部署或重启已有服务；未提交预处理或运行分析；未处理保留组。本轮独立测试集是本次明确授权的 45 条正式评测集合。", ""]
    (out / "REPORT.md").write_text("\n".join(md), encoding="utf-8")
