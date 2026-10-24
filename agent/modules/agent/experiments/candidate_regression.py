"""Compare public candidate bindings against an explicitly supplied pre-CSP source.

Uses deterministic test fixtures and an optional already-observed real profile;
no model invocation, numerical analysis or preprocessing submission.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import hashlib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
import pytest
from test_analysis_product_planner import setup_products, p
from round14_fixture import fixture as group_fixture
from test_round15_global_method import fixture as global_fixture


def signature(tools, result):
    rows = []
    for c in result["candidates"]:
        plan = tools.control_store.latest(c["candidate_id"])["record"]["plan"]
        rows.append(
            {
                "method": c["method"]["method_id"],
                "atlas": c["atlas"]["name"],
                "subjects": plan["data"]["subjects"],
                "files": sorted(plan["data"]["files"]),
                "labels": {
                    k: [r["key"] for r in v["labels"]]
                    for k, v in plan["analysis_scope"]["labels"].items()
                },
            }
        )
    return sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--legacy-source", required=True)
    a.add_argument("--output", required=True)
    a.add_argument("--real-profile")
    a.add_argument("--registry")
    args = a.parse_args()
    source = Path(args.legacy_source).read_text(encoding="utf-8")
    old = types.ModuleType(p.__package__ + ".round15_legacy_comparison")
    old.__package__ = p.__package__
    old.__file__ = p.__file__
    sys.modules[old.__name__] = old
    exec(compile(source, args.legacy_source, "exec"), old.__dict__)
    cases = ["P1_ROI", "P2_HULL", "A3", "GROUP", "GLOBAL"]
    if args.real_profile:
        cases += [
            "P1_IXI064",
            "P2_IXI064",
            "A3_IXI064",
            "GLOBAL_IXI064",
            "P1_SPACE_CHANGED_IXI064",
            "P1_SPECIES_MISMATCH_IXI064",
        ]
    results = []
    with tempfile.TemporaryDirectory(prefix="round15-candidates-") as tmp:
        for name in cases:
            with pytest.MonkeyPatch.context() as mp:
                folder = Path(tmp) / name
                folder.mkdir()
                if name == "GROUP":
                    tools, intent = group_fixture(folder, mp)
                elif name == "GLOBAL":
                    tools, intent = global_fixture(folder, mp)
                else:
                    tools = setup_products(folder, mp)
                    if name.startswith("P2"):
                        intent = {
                            "measures": ["gyrification"],
                            "regions": "global",
                            "method_id": "method:v13:global_convex_hull_gyrification",
                        }
                    elif name.startswith("GLOBAL"):
                        intent = {
                            "measures": ["globalmorphometry"],
                            "method_id": "method:v15:global_morphometry",
                        }
                    else:
                        intent = {
                            "measures": ["thickness"],
                            "comparison": (
                                "asymmetry" if name.startswith("A3") else "describe"
                            ),
                            "method_id": "method:v12:surface_annotation_roi",
                        }
                if name.endswith("IXI064"):
                    catalogue = json.loads(Path(args.registry).read_text())
                    root = next(
                        e for e in catalogue["roots"] if e["subject_id"] == "IXI064"
                    )
                    tools.input_roots = (Path(root["path"]),)
                    mp.setenv("AGENT_DATA_CATALOG", args.registry)
                    saved = json.loads(Path(args.real_profile).read_text())
                    record = saved.get("record", saved)
                    if "SPACE_CHANGED" in name or "SPECIES_MISMATCH" in name:
                        row = next(
                            f
                            for f in record["files"]
                            if f["path"]["value"].endswith("lh.thickness")
                        )
                        row["attributes"] = (
                            {"space": "fsLR_32k"}
                            if "SPACE_CHANGED" in name
                            else {"species": "chimpanzee"}
                        )
                    profile = tools.control_store.save("data_profile", record)
                    mp.setattr(
                        p,
                        "ensure_profile",
                        lambda *_, snapshot=profile: (snapshot, True),
                    )
                    intent["subjects"] = ["IXI064"]
                old.ensure_profile = p.ensure_profile
                before = signature(tools, old.plan_analysis(tools, intent))
                after_result = p.plan_analysis(tools, intent)
                after = signature(tools, after_result)
                removed = [r for r in before if r not in after]
                added = [r for r in after if r not in before]
                results.append(
                    {
                        "case": name,
                        "old_count": len(before),
                        "new_count": len(after),
                        "equal": before == after,
                        "expected_stricter": "SPACE_CHANGED" in name
                        or "SPECIES_MISMATCH" in name,
                        "constraint": (
                            "unary.space: stored/native allows unknown but rejects explicit fsLR_32k"
                            if "SPACE_CHANGED" in name
                            else (
                                "unary.species: observed product must agree with the registered human declaration"
                                if "SPECIES_MISMATCH" in name
                                else None
                            )
                        ),
                        "removed": removed,
                        "added": added,
                        "old_candidates": before,
                        "infeasible_reasons": [
                            r.get("reason") for r in after_result["infeasible"]
                        ],
                    }
                )
    report = {
        "legacy_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "cases": results,
        "equal_cases": sum(r["equal"] for r in results),
        "model_calls": 0,
        "preprocessing_submissions": 0,
    }
    with Path(args.output).open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}))
    print(
        json.dumps(
            [
                {k: r[k] for k in ["case", "old_count", "new_count", "equal"]}
                for r in results
            ]
        )
    )
    return (
        0
        if all(
            (
                r["equal"]
                if not r["expected_stricter"]
                else (r["old_count"] > 0 and r["new_count"] == 0)
            )
            for r in results
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
