"""Post-evaluation error diagnosis from preserved samples; no calls or edits to gold."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.knowledge import run_condition_test_evaluation as r


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    assert json.loads((out / "audit.json").read_text())["status"] == "audited"
    c = r.base.load_canon()
    gold = r.verify_gold()
    by_id = {i["id"]: i for i in gold["items"]}
    vocab, _ = r.v2.load_vocab()
    events = [json.loads(s) for s in (out / "requests/calls.jsonl").read_text().splitlines()]
    answers = {e["request_id"]: e for e in events if e["event"] == "end" and e.get("status") == "ok"}
    starts = {e["request_id"]: e for e in events if e["event"] == "start"}
    failed_http = []
    for e in events:
        if e["event"] != "end" or e.get("status") == "ok":
            continue
        start = starts[e["request_id"]]
        recovered = any(x["event"] == "end" and x.get("status") == "ok" and x.get("logical_id") == e["logical_id"] for x in events)
        failed_http.append({"ordinal": start["ordinal"], "arm": e["arm"], "item_id": e["item_id"],
                            "sample": e["sample"], "attempt": e["attempt"], "request_id": e["request_id"],
                            "status": e["status"], "http_status": e.get("http_status"),
                            "recovered_in_same_sample": recovered,
                            "input_tokens": e.get("input_tokens"), "output_tokens": e.get("output_tokens"),
                            "total_tokens": e.get("total_tokens")})
    r.base.save_json(out / "http_failures.json", failed_http)
    r.base.write_csv(out / "http_failures.csv", failed_http)

    errors = json.loads((out / "full_v2_errors.json").read_text(encoding="utf-8"))
    detailed = []
    for row in errors:
        item = by_id[row["id"]]
        sample_rows = []
        for record in row["sampling"]["responses"]:
            event = answers[record["request_id"]]
            match = re.search(r"\{.*\}", event["text"] or "", re.S)
            try:
                data = json.loads(match.group(0)) if match else None
            except json.JSONDecodeError:
                data = None
            entry = {"sample": record["sample"], "replacement_of": record.get("replacement_of"),
                     "request_id": record["request_id"], "finish_reason": event.get("finish_reason")}
            if not isinstance(data, dict):
                entry.update(parseable=False, problems=["no JSON object"])
            else:
                template = str(data.get("template", "advisory")).strip()
                if template in ["none", ""]:
                    template = "advisory"
                params = data.get("parameters") or {}
                problems = []
                normalised = params
                if template == "advisory":
                    normalised = None
                elif template not in c.DEFINITIONS:
                    problems = ["unknown template"]
                else:
                    try:
                        normalised, problems = c.normalise_v2(template, params, vocab)
                        if not problems:
                            problems += c.type_check_v2(template, normalised, gold["slots"], vocab)
                    except (TypeError, ValueError, AttributeError, KeyError) as error:
                        problems = [type(error).__name__]
                entry.update(parseable=True, raw_template=template, raw_parameters=params,
                             normalised_parameters=normalised, problems=problems)
            sample_rows.append(entry)
        specific = list(row["reasons"])
        rejected = sorted({problem for sample in sample_rows for problem in sample.get("problems", [])})
        if rejected:
            specific.append("实际样本检查结果：" + "；".join(rejected))
        if row["predicted_parameters"] != row["gold_parameters"] and row["predicted_template"] == row["gold_template"]:
            specific.append("同一模板的参数字面值不同，详见下列标准/预测及逐样本参数")
        if row["margin"] is not None and row["margin"] < c.V2_MARGIN and math.isclose(row["margin"], c.V2_MARGIN, abs_tol=1e-12):
            specific.append("原实现浮点 margin 略小于 0.2；按冻结代码保留 review")
        if item["pending_user_decision"]:
            specific.append("该条仍待用户决定，主报告按文件标注计分，39条敏感性集合已排除")
        detailed.append({**row, "annotation_note": item.get("annotation_note"),
                         "diagnostic_reasons": specific, "sample_diagnostics": sample_rows})
    review_path = out / "posthoc_error_review.json"
    if review_path.exists():
        notes = json.loads(review_path.read_text(encoding="utf-8"))["notes"]
        for row in detailed:
            row["specific_interpretation"] = notes.get(str(row["id"]))
    r.base.save_json(out / "full_v2_errors_detailed.json", detailed)
    md = ["# full_v2 错误清单与逐样本检查", "", "本文件为固定结果的离线诊断；无模型调用、调参或标准答案修改。", ""]
    for e in detailed:
        md += [f"## {e['id']} · {e['method']}", "", e["statement"], "", "引文：" + e["quote"], "",
               "冻结标准：" + json.dumps({"template": e["gold_template"], "parameters": e["gold_parameters"]}, ensure_ascii=False), "",
               "标注说明：" + str(e["annotation_note"]), "",
               "预测：" + json.dumps({"decision": e["predicted_decision"], "template": e["predicted_template"], "parameters": e["predicted_parameters"]}, ensure_ascii=False), "",
               "具体解释：" + str(e.get("specific_interpretation") or "见逐样本检查"), "",
               "原因：" + "；".join(e["diagnostic_reasons"]), "",
               "票数：" + json.dumps(e["votes"], ensure_ascii=False), "",
               "逐样本解析/类型检查：", "", "```json", json.dumps(e["sample_diagnostics"], ensure_ascii=False, indent=2), "```", ""]
    (out / "FULL_V2_ERRORS_DETAILED.md").write_text("\n".join(md), encoding="utf-8")
    for arm in r.ARMS:
        preds = json.loads((out / f"predictions_{arm}.json").read_text(encoding="utf-8"))
        r.base.save_json(out / f"review_queue_{arm}.json", [{"item": i, "prediction": p} for i, p in zip(gold["items"], preds) if p["decision"] == "review"])
        merged = []
        for method in sorted({i["method"] for i in gold["items"]}):
            merged += c.merge([p for p in preds if p["method"] == method and p.get("parameters") is not None], method)
        r.base.save_json(out / f"merged_{arm}.json", merged)
    print(json.dumps({"full_v2_error_items": len(detailed), "new_model_calls": 0}), flush=True)


if __name__ == "__main__":
    main()
