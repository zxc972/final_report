"""Offline calibration: existing gates/checkers only; no model and no images."""

from pathlib import Path
from collections import Counter, defaultdict
from types import SimpleNamespace
import hashlib, json, sys


def evaluate(root):
    backend = root / "cohort_b/backend_review"
    sys.path.insert(0, str(backend))
    from backend.analysis_crossspecies import load_policy
    from backend.analysis_crossspecies_templates import CHECKERS
    from backend.analysis_condition_templates import attr_equal
    from backend.analysis_feedback import FeedbackJournal
    from backend.analysis_phase_tools import phase_tools
    from backend.analysis_session import AnalysisSession
    from backend.analysis_plans import _work_path
    from backend.analysis_output_contract import validate_csv
    from backend.analysis_precision import rounded_columns
    from backend.agent_router import parse_route
    from backend.analysis_review_protocol import parse_structured_review

    location = backend / "evaluation/calibration/round12"
    raw = (location / "frozen_cases.json").read_bytes()
    expected = (location / "frozen_cases.sha256").read_text().strip()
    assert hashlib.sha256(raw).hexdigest() == expected
    corpus = json.loads(raw)
    policy = load_policy("cross_species_rules")
    policy_sha = hashlib.sha256(
        (backend / "knowledge_analysis/cross_species_rules.json").read_bytes()
    ).hexdigest()
    manifest = json.loads((location / "freeze_manifest.json").read_text())
    assert policy_sha == manifest["policy_sha256"]
    mapping = {row["template"]: row for row in policy["templates"]}
    work = root / "offline_p1"
    controls = (
        root
        / "offline_state/controls"
        / hashlib.sha256(str(work).encode()).hexdigest()[:32]
    )
    bundle_path = sorted(controls.glob("execution_bundle.v*.json"))[-1]
    table = json.loads(bundle_path.read_text())["record"]["output_contract"]["table"]
    rows = []
    for item in corpus["cases"]:
        op = item["operation"]
        payload = item["payload"]
        layer = "uncovered_semantic_review"
        detail = {}
        actual = "not_evaluated"
        if op == "cross_template":
            layer = "constraint_templates"
            instance = mapping[payload["template"]]
            detail = CHECKERS[payload["template"]](
                instance["parameters"], payload["environment"], instance["severity"]
            )
            actual = {"pass": "valid", "warn": "warning", "block": "invalid"}[
                detail["verdict"]
            ]
        elif op == "attr_equal":
            layer = "constraint_templates"
            detail = attr_equal(payload["parameters"], payload["environment"])
            actual = {"pass": "valid", "warn": "warning", "block": "invalid"}[
                detail["verdict"]
            ]
        elif op == "feedback_observation":
            layer = "execution_feedback_replay"
            actual = "invalid" if FeedbackJournal.failed(payload["result"]) else "valid"
            detail = {
                "historical_observation_only": True,
                "fresh_code_execution": False,
            }
        elif op == "phase_gate":
            layer = "execution_gate"
            allowed = phase_tools(
                SimpleNamespace(state=lambda: {"phase": payload["phase"]}), set()
            )
            actual = "valid" if payload["tool"] in allowed else "invalid"
            detail = {"available_tools": sorted(allowed)}
        elif op == "path_guard":
            layer = "execution_gate"
            session = AnalysisSession.__new__(AnalysisSession)
            session.record = {
                "phase": "sealed",
                "plan_version": 1,
                "code_path": payload["sealed"],
                "wrong_path_blocks": 0,
            }
            store = SimpleNamespace(
                latest=lambda kind: {
                    "version": 1,
                    "record": {"plan": {"code_path": payload["sealed"]}},
                },
                save=lambda *args: None,
            )
            session.tools = SimpleNamespace(control_store=store, events=None)
            try:
                session.guard_write(payload["attempted"])
                actual = "valid"
            except ValueError as error:
                actual = "invalid"
                detail = {"error": str(error)}
        elif op == "normalize_path":
            layer = "plan_path_syntax"
            try:
                path = payload["path"]
                normalized = _work_path(
                    path if path.startswith("/") else "/work/" + path
                )
                actual = "valid"
                detail = {
                    "normalized": normalized,
                    "scope": "Path syntax only, not a new complete commitment",
                }
            except ValueError as error:
                actual = "invalid"
                detail = {"error": str(error)}
        elif op == "precision":
            layer = "public_precision"
            columns = rounded_columns(
                payload["csv"].encode(), ["mean", "std_population", "median"], True
            )
            actual = "invalid" if columns else "valid"
            detail = {
                "flagged_columns": columns,
                "production_behavior": "Warn and return to executed_failed; no private reference needed",
            }
        elif op == "public_contract":
            layer = "public_contract"
            detail = validate_csv(payload["csv"].encode(), table)
            actual = "valid" if detail["status"] == "pass" else "invalid"
        elif op == "route_json":
            layer = "route_protocol"
            try:
                detail = parse_route(
                    {"choices": [{"message": {"content": payload["content"]}}]}
                )
                actual = "valid"
            except (ValueError, KeyError) as error:
                actual = "invalid"
                detail = {"error": str(error)}
        elif op == "review_json":
            layer = "review_protocol"
            try:
                detail, _ = parse_structured_review(
                    payload["content"], {"evidence_card"}, {"hard_blocks": []}
                )
                actual = "valid"
            except (ValueError, KeyError) as error:
                actual = "invalid"
                detail = {"error": str(error)}
        elif op == "semantic_review":
            detail = {
                "reason": "No real or simulated language-model semantic judgment in this API-free calibration; historical findings are not reused as a detector."
            }
        fixture_notes = []
        if op == "cross_template":
            parameters = mapping[payload["template"]]["parameters"]
            if payload["template"] == "asymmetry_flip":
                for record in payload["environment"].get("bias_checks", []):
                    if record.get("kind") not in parameters["alternatives"]:
                        fixture_notes.append(
                            "Synthetic bias-check kind is outside the registered alternatives; retain frozen truth and audit separately"
                        )
            if payload["template"] == "cross_species_measure":
                kind = payload["environment"].get("measure_kind")
                if (
                    item["expected"] == "valid"
                    and kind not in parameters["two_species_allowed"]
                    and kind != "loglog_residual"
                ):
                    fixture_notes.append(
                        "Synthetic ratio kind is outside the registered measure enum; fixture-interface mismatch, not a scientific model failure"
                    )
        rows.append(
            {
                "id": item["id"],
                "origin": item["origin"],
                "error_type": item["error_type"],
                "expected": item["expected"],
                "actual": actual,
                "layer": layer,
                "label_agreement": actual == item["expected"],
                "detected": item["expected"] in {"invalid", "warning"}
                and actual in {"invalid", "warning"},
                "missed_or_uncovered": item["expected"] in {"invalid", "warning"}
                and actual in {"valid", "not_evaluated"},
                "false_block": item["expected"] == "valid" and actual == "invalid",
                "false_warning": item["expected"] == "valid" and actual == "warning",
                "not_evaluated": actual == "not_evaluated",
                "fixture_notes": fixture_notes,
                "detail": detail,
            }
        )
    layers = {}
    for layer in sorted({row["layer"] for row in rows}):
        selected = [row for row in rows if row["layer"] == layer]
        layers[layer] = {
            "n": len(selected),
            "detected": sum(r["detected"] for r in selected),
            "missed_or_uncovered": sum(r["missed_or_uncovered"] for r in selected),
            "false_block": sum(r["false_block"] for r in selected),
            "false_warning": sum(r["false_warning"] for r in selected),
            "not_evaluated": sum(r["not_evaluated"] for r in selected),
        }
    result = {
        "frozen_sha256": expected,
        "corpus_unchanged": hashlib.sha256(
            (location / "frozen_cases.json").read_bytes()
        ).hexdigest()
        == expected,
        "policy_unchanged": policy_sha == manifest["policy_sha256"],
        "api_requests": 0,
        "real_image_computations": 0,
        "public_contract_source": str(bundle_path),
        "public_contract_source_sha256": hashlib.sha256(
            bundle_path.read_bytes()
        ).hexdigest(),
        "scope": "Known regression and synthetic baseline. Runtime observations are replayed, not regenerated; no semantic LLM score is fabricated.",
        "cases": rows,
        "per_layer": layers,
        "label_counts": dict(Counter(item["expected"] for item in corpus["cases"])),
        "fixture_interface_findings": [
            {"id": row["id"], "notes": row["fixture_notes"]}
            for row in rows
            if row["fixture_notes"]
        ],
    }
    output = root / "audit/calibration_results.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "frozen_sha256",
                    "label_counts",
                    "per_layer",
                    "fixture_interface_findings",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    evaluate(Path("/data/xuancheng/agent_round12_trial_20261022"))
