"""Compact execution instructions with a complete, public output contract."""

from .analysis_operations import operations_manifest


def returns_fields(example):
    if isinstance(example, dict) and "python_type" in example:
        kind = example["python_type"]
        if kind == "tuple":
            return "tuple(" + ",".join(returns_fields(v) for v in example.get("items", [])) + ")"
        if kind == "list":
            values = example.get("example", example.get("items", []))
            return "list[" + (returns_fields(values[0]) if values else "rows") + "]"
        if kind == "dict":
            return "/".join(example.get("fields", example.get("example", {})))
        return kind.replace("numpy.", "")
    if isinstance(example, list):
        return "list[" + (returns_fields(example[0]) if example else "rows") + "]"
    if isinstance(example, dict):
        return "/".join(example)
    return type(example).__name__


def execution_card(payload):
    bundle = payload["execution_bundle"]
    plan = payload["plan"]
    if plan["method"]["method_id"] == "method:v14:group_regional_glm":
        from .analysis_group_manifest import card
        return {"status": "committed", "version": payload["version"], "execution_card": card(plan, bundle), "state": payload.get("state")}
    names = {row["function"] for row in bundle["operations"]["calls"]}
    signatures = []
    for row in operations_manifest()["functions"]:
        if row["name"] in names:
            semantic = {"read_annotation": "labels,names,ctab", "read_surface": "vertices,faces"}
            signatures.append(row["signature"] + " -> " + semantic.get(row["name"], returns_fields(row["returns_example"])))
    table = bundle["output_contract"].get("table")
    contract = ["CSV: " + ",".join(bundle["output_contract"]["csv_columns"])]
    if table:
        contract = [
            "CSV: " + ";".join(key + ":" + kind for key, kind in table["columns"].items()),
            "Allowed (no aliases): " + ";".join(key + "=" + "|".join(map(str, values)) for key, values in table["allowed_values"].items()),
            "Identity: " + ",".join(table["identity_columns"]) + "; rows=" + str(table["expected_rows"]) + "; " + ("one/retained label/metric" if bundle.get("label_sets") else "one/hemisphere surface"),
        ]
    labels = bundle.get("label_sets", {})
    label_lines = ["Labels: " + bundle["label_sets_ref"]["path"]]
    if labels:
        first = next(iter(labels.values()))["labels"][0]
        label_lines += [
            'JSON: {"subject/hemi":group}.',
            'group: annotation/cortex_label paths; labels=[{"key":' + str(first["key"]) + ',"name":"' + first["name"] + '"}].',
            "Use group.labels: key->label_key; exact name; exclude -1/unknown.",
        ]
    else:
        label_lines += ["No parcel labels for this method."]
    lines = [
        "import primatex_ops as ops", *bundle["input_paths"], *label_lines, *signatures,
        "Code: " + plan["code_path"],
        "Outputs: " + ",".join(bundle["output_contract"]["files"]), *contract,
        "JSON: methods,limitations",
        "Precision: CSV repr or %.17g; JSON native floats. Do not round; round display only.",
        "Disclose: stored/software units; scale/history unverified; rescale yes/no; descriptive; plan versions.",
        "Full plan: " + bundle["bundle_ref"],
        "Write code now; run_python(); auto-finalize.",
    ]
    if bundle.get("asymmetry_contract"):
        lines.insert(-2, "Disclose: no flip/symmetric-template check observed; n=1 descriptive only.")
        lines.insert(-2, "AI: pair same subject/metric/name; asymmetry_index=2*(L-R)/(L+R), same signed value both rows; L+R=0 undefined; descriptive only; DOI 10.1073/pnas.1718418115.")
    if payload.get("path_normalization"):
        lines.insert(-1, "Path normalized: " + payload["path_normalization"]["original"] + " -> " + plan["code_path"])
    card = "\n".join(lines)
    if len(card) > 2200:
        raise ValueError("Execution card exceeds 2200 characters; choose a smaller analysis scope")
    return {"status": "committed", "version": payload["version"], "execution_card": card, "state": payload.get("state")}
