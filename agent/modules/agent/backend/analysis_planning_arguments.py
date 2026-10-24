"""Actionable interface validation using registered data-card identities only."""
from collections import Counter

ALL_SUBJECTS = ("全部已登记被试", "all_registered")


def registry(tools):
    saved = tools.control_store.latest("data_card") if tools.control_store else None
    rows = saved["record"].get("subjects", []) if saved else []
    from .analysis_data_card import _value
    columns = set()
    for table in saved["record"].get("participants_tables", []) if saved else []:
        columns.update(table.get("columns", []))
    profile = tools.control_store.latest("data_profile") if tools.control_store else None
    if profile:
        for item in profile["record"].get("files", []):
            metadata = _value(item.get("table", {})) or {}
            columns.update(_value(metadata.get("columns", [])) or [])
    return {"available_subjects": sorted({r["subject"] for r in rows}),
            "available_measures": sorted({name for r in rows for name in r.get("metrics", [])}),
            "available_columns": sorted(columns)}


def validate_for_planning(tools, raw):
    from .analysis_product_planner import validate_intent, normal_measure
    intent, error = validate_intent(raw)
    available = registry(tools)
    if error:
        return None, {**error, **available}
    selected = intent.subjects
    all_requested = isinstance(selected, str) and selected in ALL_SUBJECTS
    all_requested = all_requested or (isinstance(selected, list) and len(selected) == 1 and selected[0] in ALL_SUBJECTS)
    errors = []
    details = {}
    if all_requested:
        if available["available_subjects"]:
            intent = intent.model_copy(update={"subjects": available["available_subjects"]})
    elif isinstance(selected, list):
        duplicates = sorted(s for s, n in Counter(selected).items() if n > 1)
        unknown = sorted(set(selected) - set(available["available_subjects"])) if available["available_subjects"] else []
        if duplicates:
            errors.append({"field": "subjects", "message": "Duplicate registered IDs: " + ", ".join(duplicates)})
            details["duplicate_subjects"] = duplicates
        if unknown:
            errors.append({"field": "subjects", "message": "Unregistered IDs: " + ", ".join(unknown)})
            details["unknown_subjects"] = unknown
    if intent.comparison in {"group", "correlation"}:
        if intent.design is None:
            errors.append({"field": "design.effect", "message": "A tested participant-table column is required. design.covariates is an optional list; design.reference is the baseline for a categorical effect."})
        if available["available_measures"]:
            allowed = {normal_measure(m) for m in available["available_measures"]}
            bad = [m for m in intent.measures if normal_measure(m) not in allowed]
            if bad:
                errors.append({"field": "measures", "message": "Use metric names registered in the data card: " + ", ".join(available["available_measures"])})
                details["invalid_measures"] = bad
    if errors:
        return None, {"status": "needs_design" if all(e["field"] == "design.effect" for e in errors) else "error", "candidates": [], "reason": "Invalid planning arguments; planner not entered",
                      "field_errors": errors, **available, **details,
                      "subject_selection_help": "Use registered IDs exactly once, or subjects='全部已登记被试'.",
                      "argument_validation_failed": True, "planner_entered": False}
    return intent, None
