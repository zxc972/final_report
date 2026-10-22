"""Host-owned operation catalogue and deterministic per-plan input bindings."""

from __future__ import annotations
import ast
import hashlib
import json
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
    example_path = (
        SOURCE.parent.parent / "knowledge_analysis" / "operation_examples.json"
    )
    raw_examples = example_path.read_bytes()
    expected = example_path.with_suffix(".sha256").read_text().strip()
    if hashlib.sha256(raw_examples).hexdigest() != expected:
        raise ValueError("Synthetic operation examples digest mismatch")
    example_payload = json.loads(raw_examples)
    if (
        example_payload.get("synthetic_only") is not True
        or example_payload.get("library_sha256") != hashlib.sha256(raw).hexdigest()
    ):
        raise ValueError("Operation examples are not bound to this library")
    examples = example_payload["examples"]
    if set(examples) != set(FUNCTIONS):
        raise ValueError("Operation examples do not cover every public function")
    functions = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            functions.append(
                {
                    "name": node.name,
                    "signature": node.name + "(" + ast.unparse(node.args) + ")",
                    "description": ast.get_docstring(node),
                    "returns_example": examples[node.name],
                    "example_scope": "Actual synthetic call; not a subject result or reference answer",
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
    catalogue = operations_manifest()
    examples = {row["name"]: row["returns_example"] for row in catalogue["functions"]}

    def add(function, inputs, scope, note=""):
        calls.append(
            {
                "function": function,
                "inputs": inputs,
                "scope": scope,
                "note": note,
                "returns_example": examples[function],
            }
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
                elif method.endswith(("surface_mesh_area", "mesh_surface_area")):
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
        "library": {k: v for k, v in catalogue.items() if k != "functions"},
        "calls": calls,
        "custom_method_help": "read_operations returns all signatures and unit/return-value conventions",
    }


def execution_bundle(context):
    from .analysis_output_contract import table_contract
    operations = suggested_operations(context)
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
    from .analysis_asymmetry_contract import applies, definition
    asymmetry = definition() if applies(context) else None
    if asymmetry:
        columns.append("asymmetry_index")
    return {
        "asymmetry_contract": asymmetry,
        "input_paths": context["data"]["files"],
        "label_sets": labels,
        "operations": operations,
        "output_contract": {
            "files": context["outputs"],
            "csv_columns": columns,
            "table": table_contract(context, operations),
            "json_required_keys": ["methods", "limitations"],
            "report": "Describe actual method, units, exclusions, observed prerequisites, limitations and all plan versions",
        },
        "must_disclose": context.get("analysis_scope", {}).get("notices", []),
        "self_checks": "Input vector lengths, finite values, requested scope/coverage, actual counts and exclusions; no expected reference values are supplied",
        "unit_disclosure": {
            "stored_values": "Retain the supplied file values; do not relabel them as independently calibrated physical measurements",
            "software_convention": "FreeSurfer thickness convention is mm; surface areas use squared stored-coordinate units; area ratios are dimensionless",
            "physical_scale_verified": False,
            "rescale_applied_during_analysis": "Declare yes/no from the actual generated program",
            "input_rescale_history": "Unverified unless independently documented",
        },
        "next_step": "Write the sealed script with primatex_ops and run_python. The program validates files/columns and finalizes automatically; when finalized, write the reply.",
    }
