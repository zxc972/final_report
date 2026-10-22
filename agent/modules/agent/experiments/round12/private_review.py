"""Private acceptance: independent stdlib reference; never imported by Agent."""

from pathlib import Path
import csv, hashlib, json, math

ROOT = Path("/data/xuancheng/agent_round12_trial_20261022/cohort_b")


def review(case):
    folder = ROOT / "trials" / case
    response = json.loads((folder / "agent_response.json").read_text())
    metadata = response.get("metadata", {})
    scope = ROOT / "workspace/round12b-trial/output"
    relative = metadata.get("output_directory")
    result = {
        "case": case,
        "passed": False,
        "numerical_passed": False,
        "checked_parcels": 0,
        "errors": [],
        "rtol": 1e-7,
        "atol": 1e-9,
    }
    if not relative:
        result["errors"].append("No analysis output directory")
    else:
        work = (scope / relative).resolve()
        assert work.is_relative_to(scope) and not work.is_symlink()
        result["workdir"] = str(work)
        if "P1" in case:
            expected = json.loads(
                (ROOT / "private_reference/recomputed_reference.json").read_text()
            )["raw_reference"]
            path = work / "summary.csv"
            if not path.is_file():
                result["errors"].append("Declared summary.csv missing")
            else:
                rows = list(csv.DictReader(path.open()))
                actual = {}
                differences = []
                for row in rows:
                    try:
                        key = row["hemisphere"] + "/" + row["name"]
                        if key in actual:
                            raise ValueError("duplicate parcel identity")
                        actual[key] = row
                        if row["subject"] != "KM002":
                            raise ValueError("Unexpected subject")
                        if row["metric"] != "thickness":
                            raise ValueError("Unexpected metric")
                        if not row.get("units"):
                            raise ValueError("Missing units")
                    except Exception as exc:
                        result["errors"].append(str(exc))
                if set(actual) != set(expected):
                    result["errors"].append("Parcel identities/coverage mismatch")
                for key in sorted(set(actual) & set(expected)):
                    comparison = {"parcel": key, "checks": {}, "passed": True}
                    for column, ref_key in [
                        ("vertex_count", "n_vertices"),
                        ("mean", "mean"),
                        ("std_population", "sd_population"),
                        ("median", "median"),
                        ("zero_count", "zero_count"),
                    ]:
                        try:
                            value = float(actual[key][column])
                            target = expected[key][ref_key]
                            delta = abs(value - target)
                            ok = math.isfinite(value) and (
                                value == target
                                if column in {"vertex_count", "zero_count"}
                                else delta <= 1e-9 + 1e-7 * abs(target)
                            )
                            comparison["checks"][column] = {
                                "observed": value,
                                "expected": target,
                                "abs_difference": delta,
                                "passed": ok,
                            }
                            comparison["passed"] &= ok
                        except Exception as exc:
                            comparison["checks"][column] = {
                                "passed": False,
                                "error": type(exc).__name__,
                            }
                            comparison["passed"] = False
                    differences.append(comparison)
                result.update(
                    checked_parcels=len(differences),
                    passed_parcels=sum(x["passed"] for x in differences),
                    rows=len(rows),
                    per_parcel=differences,
                    summary_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                result["numerical_passed"] = (
                    len(rows) == 66
                    and len(differences) == 66
                    and all(x["passed"] for x in differences)
                    and not result["errors"]
                )
        if "P2" in case:
            reference = json.loads(
                (ROOT / "private_reference/hull_reference.json").read_text()
            )
            csv_path = work / "summary.csv"
            checks = []
            if csv_path.is_file():
                rows = list(csv.DictReader(csv_path.open()))
                observed = {row.get("hemisphere"): row for row in rows}
                if len(rows) != 2 or set(observed) != {"lh", "rh"}:
                    result["errors"].append("Hull hemisphere coverage mismatch")
                for hemi in ["lh", "rh"]:
                    for column, key in [
                        ("surface_area", "pial_area"),
                        ("hull_area", "hull_area"),
                        ("area_ratio", "ratio"),
                    ]:
                        value = float(observed.get(hemi, {}).get(column, "nan"))
                        target = reference[hemi][key]
                        passed = math.isfinite(value) and abs(
                            value - target
                        ) <= 1e-9 + 1e-7 * abs(target)
                        checks.append(
                            {
                                "hemisphere": hemi,
                                "column": column,
                                "observed": value if math.isfinite(value) else None,
                                "expected": target,
                                "passed": passed,
                            }
                        )
                result["hull_checks"] = checks
                result["numerical_passed"] = (
                    len(checks) == 6
                    and all(row["passed"] for row in checks)
                    and not result["errors"]
                )
            else:
                result["errors"].append("Hull summary missing")
        result["native_status"] = metadata.get("status")
        result["execution_exit_code"] = metadata.get("execution", {}).get("exit_code")
        result["artifact_structural_passed"] = (
            metadata.get("validation", {}).get("valid") is True
        )
        result["manifest_exists"] = (work / "analysis_manifest.json").is_file()
        auto = metadata.get("execution", {}).get("automatic_finalization", {})
        rid = auto.get("artifact_receipt_id")
        receipt_valid = False
        if isinstance(rid, str) and len(rid) == 32:
            receipt_path = (
                work.parent / ".artifact_receipts" / work.name / (rid + ".json")
            )
            if receipt_path.is_file():
                artifact_receipt = json.loads(receipt_path.read_text())
                execution_id = artifact_receipt.get("execution_receipt_id")
                execution_path = (
                    work.parent
                    / ".execution_receipts"
                    / work.name
                    / (str(execution_id) + ".json")
                )
                if execution_path.is_file():
                    execution_receipt = json.loads(execution_path.read_text())
                    receipt_valid = (
                        execution_receipt["result"].get("exit_code") == 0
                        and execution_receipt["result"].get("status") == "success"
                        and execution_receipt["script_sha256_before"]
                        == execution_receipt["script_sha256_after"]
                        and artifact_receipt["validation"].get("valid") is True
                        and hashlib.sha256(
                            (work / "analysis_manifest.json").read_bytes()
                        ).hexdigest()
                        == artifact_receipt["manifest_sha256"]
                    )
        result["automatic_finalization"] = auto.get("status") == "finalized"
        result["protected_receipts_verified"] = receipt_valid
        records = []
        for path in (ROOT / "state").rglob("context.json"):
            context = json.loads(path.read_text())
            if context.get("run_id") == metadata.get("run_id") and metadata.get(
                "run_id"
            ):
                records = [
                    json.loads(p.read_text())["record"]
                    for p in sorted(path.parent.glob("session.v*.json"))
                ]
                break
        phases = []
        for record in records:
            if not phases or phases[-1] != record["phase"]:
                phases.append(record["phase"])
        result["phase_sequence"] = phases
        result["wrong_path_blocks"] = (
            records[-1].get("wrong_path_blocks", 0) if records else 0
        )
        result["passed"] = (
            result["numerical_passed"]
            and result["automatic_finalization"]
            and result["protected_receipts_verified"]
            and result["phase_sequence"][-1:] == ["finalized"]
            and metadata.get("status") == "completed"
            and result["execution_exit_code"] == 0
            and result["artifact_structural_passed"]
            and metadata.get("validation", {}).get("independent_numeric_status")
            == "pass"
            and all(
                (work / name).is_file()
                for name in [
                    "summary.csv",
                    "summary.json",
                    "report.md",
                    "analysis_manifest.json",
                ]
            )
        )
    (folder / "private_independent_review.json").write_text(
        json.dumps(result, indent=2)
    )
    return result
