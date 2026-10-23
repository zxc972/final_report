"""Plan-bound public table contract; never contains private reference values."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from pathlib import PurePosixPath

ROI_TYPES = {
    "subject": "str", "hemisphere": "str", "metric": "str", "label_key": "int",
    "name": "str", "vertex_count": "int", "mean": "float", "std_population": "float",
    "median": "float", "zero_count": "int", "units": "str",
}
HULL_TYPES = {
    "subject": "str", "hemisphere": "str", "surface_area": "float", "hull_area": "float",
    "area_ratio": "float", "area_units": "str",
}


def table_contract(plan, operations):
    """Declare identities solely from the plan, selected inputs and label_sets."""
    method = plan["method"]["method_id"].rsplit(":", 1)[-1]
    if method == "global_morphometry":
        from .analysis_global_method import table_contract as global_contract
        return global_contract(plan)
    labels = plan.get("analysis_scope", {}).get("labels", {})
    expected = []
    if labels:
        types = dict(ROI_TYPES)
        keys = ["subject", "hemisphere", "metric", "label_key"]
        for call in operations["calls"]:
            if call["function"] != "parcel_summary":
                continue
            scope = call["scope"]
            subject, hemisphere = scope.rsplit("/", 1)
            metric = PurePosixPath(call["inputs"]["metric_path"]).suffix.lstrip(".")
            for item in labels[scope]["labels"]:
                expected.append({"subject": subject, "hemisphere": hemisphere,
                                 "metric": metric, "label_key": int(item["key"]), "name": item["name"]})
    elif method == "global_convex_hull_gyrification":
        types = HULL_TYPES
        keys = ["subject", "hemisphere"]
        subjects = plan["data"]["subjects"]
        if len(subjects) != 1:
            raise ValueError("Public hull contract requires one explicitly bound subject")
        for call in operations["calls"]:
            if call["function"] == "convex_hull_area_ratio":
                path = PurePosixPath(call["inputs"]["surface_path"])
                expected.append({"subject": subjects[0], "hemisphere": path.name.split(".")[0]})
    else:
        return None
    if not expected:
        raise ValueError("Registered method has no public output identities")
    from .analysis_asymmetry_contract import applies
    if applies(plan):
        types["asymmetry_index"] = "float"
    allowed = {key: sorted({row[key] for row in expected}, key=str)
               for key in ["subject", "hemisphere", "metric"] if key in expected[0]}
    return {
        "schema": "primatex.public_table_contract.v1",
        "columns": dict(types), "identity_columns": keys,
        "fixed_values": {key: values[0] for key, values in allowed.items() if len(values) == 1},
        "allowed_values": allowed, "expected_rows": len(expected),
        "expected_identities": expected,
        "row_rule": "One row per retained label per subject/hemisphere/metric" if labels else "One row per selected hemisphere surface",
        "extra_columns_allowed": True,
        "alias_mapping": False,
        "source": "Sealed input bindings and public label_sets, not a numerical oracle",
    }


def validate_csv(raw, contract, filename="summary.csv"):
    errors = []
    identities = []
    schema_count = 0
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    columns = reader.fieldnames or []
    missing = sorted(set(contract["columns"]) - set(columns))
    if missing:
        errors.append(f"{filename}: missing columns {','.join(missing)}")
        schema_count += len(missing)
    if contract.get("extra_columns_allowed") is False and set(columns) - set(contract["columns"]):
        schema_count += 1
        errors.append(f"{filename}: undeclared columns; aliases are not mapped")
    if len(columns) != len(set(columns)):
        errors.append(f"{filename}: duplicate column names")
        schema_count += 1
    rows = list(reader)
    expected = {tuple(str(item[key]) for key in contract["identity_columns"]): item
                for item in contract["expected_identities"]}
    seen = set()
    extras = set()
    for index, row in enumerate(rows, 2):
        parsed = {}
        for column, kind in contract["columns"].items():
            value = row.get(column)
            try:
                if value is None or not str(value).strip():
                    if column in contract.get("nullable_columns", []):
                        continue
                    raise ValueError("empty")
                if kind == "int":
                    if not re.fullmatch(r"[+-]?\d+", str(value)):
                        raise ValueError("write an integer token without decimal formatting")
                    parsed[column] = int(value)
                    if column in {"vertex_count", "zero_count"} and parsed[column] < 0:
                        raise ValueError("negative count")
                elif kind == "float":
                    parsed[column] = float(value)
                    if not math.isfinite(parsed[column]):
                        raise ValueError("non-finite")
                else:
                    parsed[column] = value
            except (ValueError, TypeError, OverflowError):
                schema_count += 1
                errors.append(f"{filename}: row {index} {column} must be finite {kind}; observed {str(value)[:70]!r}")
        if contract.get("schema") == "primatex.group_table_contract.v1":
            from .analysis_group_contract import row_errors
            for reason in row_errors(row, contract):
                schema_count += 1
                errors.append(f"{filename}: row {index} {reason}")
        for column, allowed in contract["allowed_values"].items():
            if row.get(column) not in allowed:
                schema_count += 1
                errors.append(f"{filename}: row {index} {column}={row.get(column)!r}; use {allowed!r}; aliases are not mapped")
        key = tuple(str(parsed.get(field, row.get(field, ""))) for field in contract["identity_columns"])
        if key in seen:
            identities.append({"kind": "duplicate", "identity": key})
        seen.add(key)
        if key not in expected:
            extras.add(key)
        elif "name" in expected[key] and row.get("name") != expected[key]["name"]:
            identities.append({"kind": "label_name", "identity": key})
            errors.append(f"{filename}: row {index} name must match label_sets ({expected[key]['name']!r})")
    absent = set(expected) - seen
    identities.extend({"kind": "missing", "identity": key} for key in sorted(absent))
    identities.extend({"kind": "unexpected", "identity": key} for key in sorted(extras))
    if len(rows) != contract["expected_rows"]:
        errors.append(f"{filename}: expected {contract['expected_rows']} rows, observed {len(rows)}")
        schema_count += 1
    if identities:
        errors.append(f"{filename}: {len(identities)} identity differences; use the sealed label_sets without aliases")
    return {
        "status": "fail" if errors or identities else "pass", "file": filename,
        "rows": len(rows), "expected_rows": contract["expected_rows"],
        "schema_mismatch_count": schema_count, "identity_mismatch_count": len(identities),
        "numeric_mismatch_count": 0, "errors": errors[:24],
        "identity_differences": identities[:12],
        "scope": "Public serialization/identity contract, not numerical reference verification",
    }


def check_outputs(tools):
    from .analysis_agent import _read_regular, _write_regular
    from .analysis_validation import MAX_ARTIFACT_BYTES

    saved = tools.control_store.latest("execution_bundle")
    plan = tools.control_store.latest("plan")
    bundle = saved["record"]
    binding = {"plan_sha256": plan["sha256"], "execution_receipt_id": tools.last_execution.get("receipt_id")}
    if bundle.get("plan_sha256") != plan["sha256"]:
        raise ValueError("Public contract bundle does not match current sealed plan")
    table = bundle["output_contract"].get("table")
    results = []
    if table:
        for item in bundle["output_contract"]["files"]:
            filename = item if isinstance(item, str) else item["path"]
            if not filename.endswith(".csv"):
                continue
            target = tools.resolve("/work/" + filename.removeprefix("/work/"), writable=True)
            raw = _read_regular(target, tools.workdir, MAX_ARTIFACT_BYTES)
            declared = bundle["output_contract"].get("tables", {}).get(filename, table)
            result = validate_csv(raw, declared, filename)
            result["output_sha256"] = hashlib.sha256(raw).hexdigest()
            results.append(result)
    summary = {**binding, "status": "fail" if any(r["status"] == "fail" for r in results) else "pass" if results else "not_configured",
               "schema_mismatch_count": sum(r["schema_mismatch_count"] for r in results),
               "identity_mismatch_count": sum(r["identity_mismatch_count"] for r in results),
               "numeric_mismatch_count": 0, "files": results}
    tools.control_store.save("public_output_validation", summary)
    if summary["status"] == "fail":
        path = tools.resolve("/work/tool_results/validation_feedback.json", writable=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_regular(path, tools.workdir, json.dumps({"public_output_contract": summary,
            "next": "Edit the sealed script to match the public contract; rerun. Do not alias-map the output."}, ensure_ascii=False))
    return summary


def current_summary(tools):
    saved = tools.control_store.latest("public_output_validation")
    plan = tools.control_store.latest("plan")
    if not saved or not plan:
        return {"status": "not_performed", "identity_mismatch_count": 0, "numeric_mismatch_count": 0}
    record = saved["record"]
    if record["plan_sha256"] != plan["sha256"] or record["execution_receipt_id"] != tools.last_execution.get("receipt_id"):
        return {"status": "not_performed", "identity_mismatch_count": 0, "numeric_mismatch_count": 0}
    return record
