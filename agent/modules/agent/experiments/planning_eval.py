#!/usr/bin/env python3
"""Freeze expected perturbations first, then evaluate a real profile offline.

No model, filesystem mutation of inputs, preprocessing execution or network call.
Run --freeze MANIFEST before --run MANIFEST --output CSV. A manifest binds the
profile, registration, observed software, rules and knowledge by SHA-256.
"""
from __future__ import annotations
import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.analysis_matching_adapter import inventory, match, planning_targets
from backend.analysis_completion_adapter import completion

DOCUMENTS = (
    "method_requirements",
    "condition_templates",
    "product_types",
    "workflow_steps",
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp(args):
    return {
        "profile": sha(args.profile),
        "registry": sha(args.registry),
        "software": sha(args.software) if args.software else None,
        "rules": sha(args.rules),
        "knowledge": {
            name: sha(ROOT / "knowledge_analysis" / (name + ".json"))
            for name in DOCUMENTS
        },
    }


def select(product, selector, h):
    return all(
        (
            h.subsumes(value, product["type"])
            if key == "type"
            else product["attrs"].get(key) == value
        )
        for key, value in selector.items()
    )


def perturb(products, entries, software, operations, h):
    products, entries, software = copy.deepcopy((products, entries, software))
    for op in operations:
        kind = op["op"]
        if kind == "software":
            software[op["command"]] = op["available"]
        elif kind == "declaration":
            for e in entries:
                e["species_declared"] = op["species"]
            for p in products:
                p["attrs"]["species"] = op["species"]
        elif kind in {"delete", "set"}:
            chosen = [p for p in products if select(p, op["select"], h)]
            if not chosen:
                raise ValueError("Perturbation matched no product: " + json.dumps(op))
            if kind == "delete":
                products = [p for p in products if p not in chosen]
            else:
                for p in chosen:
                    p["attrs"].update(op["attributes"])
        else:
            raise ValueError("Unsupported perturbation: " + str(kind))
    return products, entries, software


def missing_signature(result):
    return sorted(
        "|".join(m.get("types", [m["type"]]))
        + "@"
        + next((c["value"] for c in m["unary"] if c["attr"] == "hemisphere"), "global")
        for m in result["missing"]
    )


def run(args, manifest):
    if stamp(args) != manifest["input_sha256"] or args.subject != manifest["subject"]:
        raise ValueError(
            "Frozen inputs, rules or knowledge changed; create a new reviewed freeze"
        )
    docs = {
        name: read(ROOT / "knowledge_analysis" / (name + ".json")) for name in DOCUMENTS
    }
    for name in DOCUMENTS:
        expected = (
            (ROOT / "knowledge_analysis" / (name + ".sha256")).read_text().split()[0]
        )
        if expected != manifest["input_sha256"]["knowledge"][name]:
            raise ValueError("Knowledge digest mismatch: " + name)
    profile = read(args.profile)
    profile = profile.get("record", profile)
    registry = read(args.registry)
    entries = [
        {**e, "index": i}
        for i, e in enumerate(registry["roots"])
        if e["subject_id"] == args.subject
    ]
    if len(entries) != 1:
        raise ValueError("Exactly one registered subject is required")
    products = inventory(profile, entries)
    products = [p for p in products if p["attrs"].get("subject") == args.subject]
    if not products:
        raise ValueError("Profile does not contain the selected registered subject")
    raw_software = read(args.software) if args.software else {}
    software = raw_software.get("software", raw_software)
    from backend.analysis_csp_matching import TypeHierarchy

    hierarchy = TypeHierarchy.from_document(docs["product_types"])
    rows = []
    for state in manifest["rules"]["states"]:
        start = time.perf_counter()
        altered, declarations, observed = perturb(
            products, entries, software, state["perturbations"], hierarchy
        )
        spec = next(
            s
            for s in docs["method_requirements"]["methods"]
            if s["method_id"] == state["method_id"]
        )
        result = match(
            spec,
            declarations,
            altered,
            state["intent"],
            state.get("atlas"),
            docs["condition_templates"],
            docs["product_types"],
        )
        matched = time.perf_counter()
        targets = planning_targets(result, spec, declarations)
        plan = completion(
            targets,
            altered,
            docs["workflow_steps"],
            result["problem"]["hierarchy"],
            observed,
        )
        finished = time.perf_counter()
        candidate_count = (
            len(result["solutions"])
            if spec["execution_scope"] == "supplied_derivatives"
            else 0
        )
        missing = missing_signature(result)
        expected = state["expected"]
        candidate_ok = candidate_count == expected["candidate_count"]
        missing_ok = missing == sorted(expected["missing"])
        rows.append(
            {
                "state": state["id"],
                "family": state["family"],
                "subject": args.subject,
                "candidate_count": candidate_count,
                "candidate_correct": candidate_ok,
                "missing": json.dumps(missing, ensure_ascii=False),
                "missing_correct": missing_ok,
                "matching_conflict": bool(result["conflicts"]),
                "completion_feasible": plan["feasible"],
                "completion_cost": plan["cost"],
                "steps": json.dumps(plan["steps"]),
                "unknown_software": json.dumps(plan["unknown_software"]),
                "exact_cost": plan["optimality_check"]["cost"],
                "optimal_consistent": plan["optimality_check"]["consistent"],
                "matching_ms": round((matched - start) * 1000, 3),
                "planning_ms": round((finished - matched) * 1000, 3),
                "total_ms": round((finished - start) * 1000, 3),
                "reason_chain": json.dumps(plan["reason_chain"], ensure_ascii=False),
                "search_nodes": result["matching_stats"]["search_nodes"],
                "pruned": result["matching_stats"]["pruned"],
                "frozen_sha256": sha(args.run),
                "model_calls": 0,
                "preprocessing_submissions": 0,
            }
        )
    with Path(args.output).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "states": len(rows),
        "candidate_correct": sum(r["candidate_correct"] for r in rows),
        "missing_correct": sum(r["missing_correct"] for r in rows),
        "optimal_consistent": sum(r["optimal_consistent"] for r in rows),
        "nonempty_plans": sum(bool(json.loads(r["steps"])) for r in rows),
        "median_ms": statistics.median(r["total_ms"] for r in rows),
        "max_ms": max(r["total_ms"] for r in rows),
        "profile_sha256": manifest["input_sha256"]["profile"],
        "frozen_sha256": sha(args.run),
        "csv_sha256": sha(args.output),
        "model_calls": 0,
        "preprocessing_submissions": 0,
        "scope": "Typed matching/completion correctness; not numerical analysis, anatomical QC or workflow execution validation.",
    }
    with Path(args.output).with_suffix(".summary.json").open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False))
    return (
        0
        if all(
            r["candidate_correct"] and r["missing_correct"] and r["optimal_consistent"]
            for r in rows
        )
        else 1
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--software")
    parser.add_argument(
        "--rules", default=str(Path(__file__).with_name("planning_perturbations.json"))
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze")
    mode.add_argument("--run")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.freeze:
        rules = read(args.rules)
        ids = [s["id"] for s in rules["states"]]
        if len(ids) != len(set(ids)) or len(ids) < 20:
            raise ValueError("At least 20 distinct frozen states required")
        manifest = {
            "schema": "planning-eval.freeze.v1",
            "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "subject": args.subject,
            "input_sha256": stamp(args),
            "rules": rules,
            "solver_run_during_freeze": False,
        }
        with Path(args.freeze).open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
        print(
            json.dumps(
                {"frozen": args.freeze, "sha256": sha(args.freeze), "states": len(ids)}
            )
        )
        return 0
    if not args.output:
        parser.error("--run requires --output")
    return run(args, read(args.run))


if __name__ == "__main__":
    raise SystemExit(main())
