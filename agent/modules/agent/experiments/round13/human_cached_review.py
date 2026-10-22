"""External comparison against a pre-run stdlib reference; no model feedback."""
from pathlib import Path
import csv
import hashlib
import json
import math

ROOT = Path("/data/xuancheng/agent_round13_trial_20261022")


def review_human(case):
    folder = ROOT / "trials" / case
    response = json.loads((folder / "agent_response.json").read_text())
    metadata = response.get("metadata", {})
    scope = ROOT / "workspace/round13-trial/output"
    result = {"case": case, "passed": False, "checked_rows": 0, "checked_scalars": 0,
              "identity_mismatches": [], "numeric_mismatches": [], "errors": [],
              "scope": "Cached pre-run independent stdlib reference; same reference implementation family as host, independent of primatex_ops and generated code"}
    relative = metadata.get("output_directory")
    if not relative:
        result["errors"].append("No output directory")
    else:
        work = (scope / relative).resolve()
        assert work.is_relative_to(scope) and not work.is_symlink()
        target = work / "summary.csv"
        which = "H2" if "_H2_" in case else "H1"
        reference_path = ROOT / "private_reference" / ("100610_" + which + "_roi_reference.json")
        expected = json.loads(reference_path.read_text())["rows"]
        if not target.is_file():
            result["errors"].append("No declared summary.csv")
        else:
            observed = list(csv.DictReader(target.open()))
            keys = ["subject", "hemisphere", "metric", "label_key", "name"]
            identity = lambda row: tuple(str(row[field]) for field in keys)
            output = {identity(row): row for row in observed}
            reference = {identity(row): row for row in expected}
            result["identity_mismatches"] = [list(key) for key in sorted(set(reference) ^ set(output))]
            if len(output) != len(observed):
                result["errors"].append("Duplicate output identity")
            columns = ["vertex_count", "mean", "std_population", "median", "zero_count"] + (["asymmetry_index"] if which == "H2" else [])
            for key in sorted(set(reference) & set(output)):
                result["checked_rows"] += 1
                for field in columns:
                    result["checked_scalars"] += 1
                    try:
                        value, expected_value = float(output[key][field]), reference[key][field]
                        passed = math.isfinite(value) and abs(value-expected_value) <= 1e-9+1e-7*abs(expected_value)
                        if field in {"vertex_count", "zero_count"}:
                            passed = value == expected_value
                    except (TypeError, ValueError, KeyError):
                        passed = False
                    if not passed:
                        result["numeric_mismatches"].append({"identity": key, "column": field})
            result["output_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
            result["reference_sha256"] = hashlib.sha256(reference_path.read_bytes()).hexdigest()
            result["passed"] = not result["errors"] and not result["identity_mismatches"] and not result["numeric_mismatches"] and result["checked_rows"] == len(expected) == 62
    (folder / "external_human_review.json").write_text(json.dumps(result, indent=2))
    return {key: value for key, value in result.items() if key not in {"identity_mismatches", "numeric_mismatches"}}
