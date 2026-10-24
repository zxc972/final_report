"""Protected host verification; reference values never enter work or model messages."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from .analysis_numeric_reference import roi_rows

RTOL = 1e-7
ATOL = 1e-9
REGISTERED = {"surface_annotation_roi", "global_convex_hull_gyrification", "group_regional_glm", "global_morphometry"}


def public_model_validation(value):
    """Remove host comparison/card data before tool feedback or model review."""
    if isinstance(value, list):
        return [public_model_validation(item) for item in value]
    if isinstance(value, dict):
        return {key: public_model_validation(item) for key, item in value.items()
                if key not in {"independent_numeric", "independent_numeric_status", "conclusion_card"}}
    return value


def compare_rows(expected, observed, keys, columns):
    def index(rows):
        mapped = {}
        for row in rows:
            key = tuple(str(row[field]) for field in keys)
            if key in mapped:
                raise ValueError("Duplicate output identity")
            mapped[key] = row
        return mapped
    reference, output = index(expected), index(observed)
    differences = []
    checked = 0
    for key in sorted(set(reference) | set(output)):
        if key not in reference or key not in output:
            differences.append({"identity": key, "reason": "coverage"})
            continue
        for column in columns:
            checked += 1
            try:
                target = reference[key][column]
                if target is None:
                    valid = output[key].get(column) in (None, "")
                    value = None
                    if not valid:
                        differences.append({"identity": key, "column": column, "observed": None, "expected": None})
                    continue
                if isinstance(target, str):
                    valid = output[key].get(column) == target
                    value = output[key].get(column)
                    if not valid:
                        differences.append({"identity": key, "column": column, "observed": value, "expected": target})
                    continue
                value = float(output[key][column])
                valid = math.isfinite(value) and abs(value-target) <= ATOL+RTOL*abs(target)
                if column in {"vertex_count", "zero_count"}:
                    valid = value == target
            except (KeyError, TypeError, ValueError):
                value, target, valid = None, reference[key].get(column), False
            if not valid:
                differences.append({"identity": key, "column": column, "observed": value if value is not None and math.isfinite(value) else None, "expected": target})
    return {"status": "fail" if differences else "pass", "checked": checked,
            "mismatch_count": len(differences), "differences": differences,
            "identity_mismatch_count": sum(row.get("reason") == "coverage" for row in differences),
            "numeric_mismatch_count": sum("column" in row for row in differences)}


def reference_rows(tools, plan, bundle, method):
    if method == "global_morphometry":
        from .analysis_global_host import reference_rows as global_rows
        return global_rows(tools, plan)
    if method == "group_regional_glm":
        from .analysis_group_design import participants
        from .analysis_group_stats import regional_glm
        regional = roi_rows(plan, bundle, tools.resolve)
        group = regional_glm(regional, participants(tools, plan["analysis_scope"]), plan["analysis_scope"]["design_terms"])
        return {
            "regional_values.csv": (regional, ["subject", "hemisphere", "metric", "label_key", "name"], ["vertex_count", "mean", "std_population", "median", "zero_count"]),
            "group_results.csv": (group["rows"], ["hemisphere", "metric", "label_key", "name"], ["n", "effect", "estimate", "se", "t", "df", "p", "q_fdr", "effect_size", "effect_size_kind", "status"]),
        }
    if method == "surface_annotation_roi":
        rows = roi_rows(plan, bundle, tools.resolve)
        columns = ["vertex_count", "mean", "std_population", "median", "zero_count"]
        from .analysis_asymmetry_contract import applies, independent_indices
        if applies(plan):
            indices = independent_indices(rows)
            for row in rows:
                row["asymmetry_index"] = indices[(row["subject"], row["metric"], row["name"])]
            columns.append("asymmetry_index")
        return rows, ["subject", "hemisphere", "metric", "label_key", "name"], columns
    rows = []
    executable = os.environ.get("ANALYSIS_REFERENCE_PYTHON", sys.executable)
    source = Path(__file__).with_name("analysis_numeric_reference.py")
    for call in bundle["operations"]["calls"]:
        if call["function"] != "convex_hull_area_ratio":
            continue
        path = call["inputs"]["surface_path"]
        if path not in plan["data"]["files"]:
            raise ValueError("Unsealed hull input")
        target = tools.resolve(path)
        result = subprocess.run([executable, "-I", "-B", str(source), "--hull", str(target)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
                                env={"PATH": "/usr/bin:/bin", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"})
        if result.returncode:
            raise RuntimeError("Host hull reference worker failed")
        values = json.loads(result.stdout)
        subject = plan["data"]["subjects"]
        if len(subject) != 1:
            raise ValueError("Explicit subject binding required for hull")
        hemisphere = Path(path).name.split(".", 1)[0]
        if hemisphere not in {"lh", "rh"}:
            raise ValueError("Explicit hemisphere binding required")
        rows.append({"subject": subject[0], "hemisphere": hemisphere, **values})
    if not rows:
        raise ValueError("No registered hull binding")
    return rows, ["subject", "hemisphere"], ["surface_area", "hull_area", "area_ratio"]


def verify(tools):
    """Host-only entry after actual receipt-backed automatic finalization."""
    plan_record = tools.control_store.latest("plan")
    execution = tools.last_execution
    bundle = tools.control_store.latest("execution_bundle")["record"]
    plan = plan_record["record"]["plan"]
    method = plan["method"]["method_id"].rsplit(":", 1)[-1]
    binding = {"plan_sha256": plan_record["sha256"], "execution_receipt_id": execution.get("receipt_id")}
    summary = {"host_verified": False, "status": "not_configured", "assessment_status": "not_assessed", "checked": None, "mismatch_count": None, "identity_mismatch_count": None, "numeric_mismatch_count": None}
    private = {**binding, "method": method, "atol": ATOL, "rtol": RTOL,
               "reference_source_sha256": hashlib.sha256(Path(__file__).with_name("analysis_numeric_reference.py").read_bytes()).hexdigest()}
    if method in REGISTERED:
        reference_ready = False
        try:
            if not binding["execution_receipt_id"] or execution.get("exit_code") != 0:
                raise ValueError("A successful current execution receipt is required")
            inputs = {path: hashlib.sha256(tools.resolve(path).read_bytes()).hexdigest() for path in plan["data"]["files"]}
            if plan.get("analysis_scope", {}).get("region_overlap_evidence"):
                from .analysis_product_planner import load_knowledge
                from .analysis_region_overlap import recheck
                mapping, mapping_sha = load_knowledge("lobar_mapping", tools)
                private["region_overlap_recheck"] = recheck(plan, tools.resolve, mapping["records"], mapping_sha)
            references = reference_rows(tools, plan, bundle, method)
            reference_ready = True
            csv_files = [path if isinstance(path, str) else path["path"] for path in bundle["output_contract"]["files"]
                         if (path if isinstance(path, str) else path["path"]).endswith('.csv')]
            if method != "group_regional_glm":
                if len(csv_files) != 1:
                    raise ValueError("Registered method must declare its reference CSV")
                references = {csv_files[0]: references}
            if set(references) != set(csv_files):
                raise ValueError("Declared CSVs must match method references")
            from .analysis_agent import _read_regular
            from .analysis_validation import MAX_ARTIFACT_BYTES
            comparisons = {}
            reference_tables = {}
            output_digests = {}
            for filename in csv_files:
                expected, keys, columns = references[filename]
                target = tools.resolve('/work/'+filename.removeprefix('/work/'), writable=True)
                raw = _read_regular(target, tools.workdir, MAX_ARTIFACT_BYTES)
                observed = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
                comparisons[filename] = compare_rows(expected, observed, keys, columns)
                reference_tables[filename] = expected
                output_digests[filename] = hashlib.sha256(raw).hexdigest()
            after = {path: hashlib.sha256(tools.resolve(path).read_bytes()).hexdigest() for path in inputs}
            if inputs != after:
                raise ValueError("Reference input changed during comparison")
            combined = {key: sum(c[key] for c in comparisons.values()) for key in ('checked','mismatch_count','identity_mismatch_count','numeric_mismatch_count')}
            combined['status'] = 'fail' if any(c['status']=='fail' for c in comparisons.values()) else 'pass'
            private.update(input_sha256=inputs, output_sha256=output_digests, expected=reference_tables, tables=comparisons, **combined)
            summary.update(host_verified=True, assessment_status="assessed", **combined)
            if method == "group_regional_glm":
                summary['tables'] = {name: {k:c[k] for k in ('status','checked','mismatch_count','identity_mismatch_count','numeric_mismatch_count')} for name,c in comparisons.items()}
                private['group_reference_source_sha256'] = hashlib.sha256(Path(__file__).with_name('analysis_group_stats.py').read_bytes()).hexdigest()
        except Exception as exc:
            private.update(reference_error_type=type(exc).__name__, reference_error=str(exc)[:500])
            if reference_ready:
                summary.update(host_verified=True, status='fail', mismatch_count=1)
                private['status']='fail'
            else:
                summary['reference_status']='unavailable' 
    saved = tools.control_store.save('independent_numeric_private', private)
    summary['evidence_ref']='independent_numeric_private.v%06d.json'%saved['version']
    trusted = tools.control_store.latest('crossspecies_observations')
    record = dict(trusted['record']) if trusted else {}
    record.update(binding, independent_numeric=summary)
    tools.control_store.save('crossspecies_observations', record)
    tools.control_store.save('independent_numeric', {**binding, **summary})
    if method == "global_morphometry":
        private['global_reference_source_sha256'] = hashlib.sha256(Path(__file__).with_name('analysis_global_reference.py').read_bytes()).hexdigest()
        tools.control_store.save('global_reference_binding', private)
        from .analysis_global_host import bind_observations
        bind_observations(tools, summary)
    return summary


def current_summary(tools):
    saved = tools.control_store.latest('independent_numeric')
    plan = tools.control_store.latest('plan')
    if not saved or not plan:
        return {"host_verified":False,"status":"not_configured","assessment_status":"not_assessed","checked":None,"mismatch_count":None,"identity_mismatch_count":None,"numeric_mismatch_count":None}
    record = saved['record']
    if record.get('plan_sha256') != plan['sha256'] or record.get('execution_receipt_id') != tools.last_execution.get('receipt_id'):
        return {"host_verified":False,"status":"not_configured","assessment_status":"not_assessed","checked":None,"mismatch_count":None,"identity_mismatch_count":None,"numeric_mismatch_count":None}
    return {key:value for key,value in record.items() if key not in {'plan_sha256','execution_receipt_id'}}


def result_card(tools, text):
    from .analysis_crossspecies import conclusion_card
    if getattr(tools, "execution_required", True) is False:
        inspected = tools.control_store.latest("inspection_result")
        valid = inspected and inspected["record"].get("passed") is True
        from .analysis_inspection import render
        return {"conclusion_text": render(inspected["record"]) if valid else "Inspection not verified.", "verdict": "qualified" if valid else "deferred",
                "reason": "Protected metadata inspection only; no scientific computation",
                "checks_passed": [{"constraint_id": "inspection_evidence", "verdict": "pass"}] if valid else [],
                "checks_not_passed": [] if valid else [{"constraint_id": "inspection_evidence", "verdict": "warn"}],
                "not_passed_count": 0 if valid else 1,
                "scope": "Metadata identities and copied values only"}
    from .analysis_constraint_binding import resolve
    constraints, binding = resolve(tools)
    checks=constraints['record']['rows'] if constraints else []
    plan = tools.control_store.latest("plan")
    from .analysis_region_overlap import conclusion_checks, attach_card
    context = plan["record"]["plan"] if plan else {}
    checks = [*checks, *conclusion_checks(context)]
    if plan and plan["record"]["plan"]["method"]["method_id"] == "method:v14:group_regional_glm":
        from .analysis_group_reporting import conclusion
        card = conclusion(tools, text, checks, current_summary(tools))
        card['constraint_binding'] = binding
        return attach_card(card, context)
    card = conclusion_card(text or 'No Agent interpretation was supplied.', 'supplied_descriptive', checks,
                           {'independent_numeric':current_summary(tools)}, ['supplied_descriptive'])
    card['constraint_binding'] = binding
    return attach_card(card, context)
