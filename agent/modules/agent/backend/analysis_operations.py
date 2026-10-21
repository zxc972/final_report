"""Host-owned operation catalogue and deterministic per-plan input bindings."""

from __future__ import annotations
import ast
import hashlib
from pathlib import Path

SOURCE = Path(__file__).with_name("primatex_ops.py")
FUNCTIONS = (
    "read_surface",
    "read_surface_metric",
    "read_annotation",
    "read_label",
    "read_label_gifti",
    "vertex_area",
    "parcel_summary",
    "read_stats_table",
    "convex_hull_area_ratio",
    "nifti_info",
)


def operations_manifest():
    raw = SOURCE.read_bytes()
    tree = ast.parse(raw.decode("utf-8-sig"))
    functions = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            functions.append(
                {
                    "name": node.name,
                    "signature": node.name + "(" + ast.unparse(node.args) + ")",
                    "description": ast.get_docstring(node),
                }
            )
    if {item["name"] for item in functions} != set(FUNCTIONS):
        raise ValueError("Operation catalogue and source disagree")
    return {
        "module": "primatex_ops",
        "version": "1.0.0",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "read_only": True,
        "import_statement": "import primatex_ops as ops",
        "functions": functions,
        "scope": "Mature format readers and basic operations; Agent writes the complete analysis program",
    }


def suggested_operations(context):
    calls = []

    def add(function, inputs, scope, note=""):
        calls.append(
            {"function": function, "inputs": inputs, "scope": scope, "note": note}
        )

    files = context["data"]["files"]
    method = context["method"]["method_id"]
    for scope, group in context.get("analysis_scope", {}).get("labels", {}).items():
        ann = group["annotation"]
        hemi = scope.rsplit("/", 1)[1]
        prefix = ann.split("/label/")[0] + "/surf/" + hemi + "."
        metrics = [
            path
            for path in files
            if path.startswith(prefix)
            and Path(path).name.split(".")[-1]
            in {"thickness", "curv", "sulc", "area", "volume", "lgi"}
        ]
        add(
            "read_annotation",
            {"path": ann},
            scope,
            "Returns positional label keys, decoded names, RGBT table; -1 is unassigned",
        )
        add(
            "read_label",
            {"path": group["cortex_label"]},
            scope,
            "Returns cortex vertex indices; pass as mask to parcel_summary",
        )
        for path in metrics:
            add(
                "read_surface_metric",
                {"path": path},
                scope,
                "Stored values, no rescaling",
            )
            add(
                "parcel_summary",
                {
                    "metric_path": path,
                    "annotation_path": ann,
                    "label_set_scope": scope,
                    "mask_path": group["cortex_label"],
                    "weights": None,
                },
                scope,
                "Use the reader return arrays and label_sets JSON group.labels; unweighted means, population SD",
            )
    if not calls:
        for path in files:
            if path.endswith((".pial", ".white")):
                add(
                    "read_surface",
                    {"path": path},
                    path,
                    "Preserve all original vertices and faces",
                )
                if method.endswith("global_convex_hull_gyrification"):
                    add(
                        "convex_hull_area_ratio",
                        {"surface_path": path},
                        path,
                        "Pass vertices, faces; full surface, not lGI",
                    )
                elif method.endswith("mesh_surface_area"):
                    add(
                        "vertex_area",
                        {"surface_path": path},
                        path,
                        "Sum barycentric vertex areas for mesh total",
                    )
            elif path.endswith((".thickness", ".curv", ".sulc", ".area")):
                add("read_surface_metric", {"path": path}, path)
            elif path.endswith((".mgz", ".nii", ".nii.gz")):
                add("nifti_info", {"path": path}, path)
            elif path.endswith(".stats"):
                add("read_stats_table", {"path": path}, path)
    return {
        "library": {k: v for k, v in operations_manifest().items() if k != "functions"},
        "calls": calls,
        "custom_method_help": "read_operations returns all signatures and unit/return-value conventions",
    }


def execution_bundle(context):
    labels = context.get("analysis_scope", {}).get("labels", {})
    hull = context["method"]["method_id"].endswith("global_convex_hull_gyrification")
    columns = (
        [
            "subject",
            "hemisphere",
            "surface_area",
            "hull_area",
            "area_ratio",
            "area_units",
        ]
        if hull
        else [
            "subject",
            "hemisphere",
            "metric",
            "label_key",
            "name",
            "vertex_count",
            "mean",
            "std_population",
            "median",
            "zero_count",
            "units",
        ]
    )
    return {
        "input_paths": context["data"]["files"],
        "label_sets": labels,
        "operations": suggested_operations(context),
        "output_contract": {
            "files": context["outputs"],
            "csv_columns": columns,
            "json_required_keys": ["methods", "limitations"],
            "report": "Describe actual method, units, exclusions, observed prerequisites, limitations and all plan versions",
        },
        "must_disclose": context.get("analysis_scope", {}).get("notices", []),
        "self_checks": "Input vector lengths, finite values, requested scope/coverage, actual counts and exclusions; no expected reference values are supplied",
        "next_step": "Write the committed script with primatex_ops, execute, check outputs and finalize_artifacts; do not hand-code binary readers",
    }
