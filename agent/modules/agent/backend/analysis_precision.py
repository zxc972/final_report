"""Public serialization heuristic; no oracle values or numerical tolerances."""

import csv
import io
from decimal import Decimal, InvalidOperation

FLOAT_COLUMNS = {
    "global_morphometry": ("mean_thickness_mm", "hull_ratio", "stored_mean_thickness_mm", "stored_hull_ratio"),
    "surface_annotation_roi": ("mean", "std_population", "median"),
    "group_regional_glm": ("mean", "std_population", "median", "estimate", "se", "t", "p", "q_fdr", "effect_size"),
    "global_convex_hull_gyrification": ("surface_area", "hull_area", "area_ratio"),
}


def rounded_columns(raw, columns, source_is_float):
    if not source_is_float:
        return []
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if not rows:
        return []
    flagged = []
    for column in columns:
        values = []
        for row in rows:
            try:
                value = Decimal(row[column])
                if not value.is_finite():
                    break
                values.append(max(0, -value.as_tuple().exponent))
            except (KeyError, TypeError, InvalidOperation):
                break
        else:
            if values and all(places <= 6 for places in values):
                flagged.append(column)
    return flagged if columns and len(flagged) == len(columns) else []


def check_precision(tools, specs):
    plan = tools.control_store.latest("plan")["record"]["plan"]
    method = plan["method"]["method_id"].rsplit(":", 1)[-1]
    columns = FLOAT_COLUMNS.get(method, ())
    if not columns:
        return []
    source_is_float = False
    for path in plan["data"]["files"]:
        target = tools.resolve(path)
        with target.open("rb") as stream:
            # FreeSurfer new curv-type vectors and triangle coordinate files
            # contain IEEE float32. Names alone are not storage evidence.
            magic = stream.read(3)
        if magic in {b"\xff\xff\xff", b"\xff\xff\xfe"}:
            source_is_float = True
    warnings = []
    for spec in specs:
        if spec.get("kind") != "csv":
            continue
        if method == "group_regional_glm":
            columns = ("mean", "std_population", "median") if spec["path"] == "regional_values.csv" else ("estimate", "se", "t", "p", "q_fdr", "effect_size")
        target = tools.resolve("/work/" + spec["path"], writable=True)
        from .analysis_agent import _read_regular
        from .analysis_validation import MAX_ARTIFACT_BYTES
        raw = _read_regular(target, tools.workdir, MAX_ARTIFACT_BYTES)
        flagged = rounded_columns(raw, columns, source_is_float)
        if flagged:
            warnings.append({"status": "warn", "message": "numeric output appears rounded",
                             "file": spec["path"], "columns": flagged,
                             "policy": "Public serialization heuristic, not an independent reference comparison"})
    return warnings
