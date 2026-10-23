"""Deterministic initial data card, bounded separately from the full profile."""

from __future__ import annotations
import json
from pathlib import Path
import re


def _value(field):
    return field.get("value") if isinstance(field, dict) else field


def summarize(profile, entries, runtime):
    rows = []
    for entry in entries:
        prefix = f"/inputs/{entry['index']}/"
        files = [
            item
            for item in profile.get("files", [])
            if str(_value(item.get("path"))).startswith(prefix)
        ]
        formats = sorted({str(_value(item.get("format"))) for item in files})
        metrics = sorted(
            {
                Path(_value(item["path"])).name.split(".", 1)[-1]
                for item in files
                if _value(item.get("format")) == "surface_metric"
            }
        )
        atlases = sorted(
            {
                Path(_value(item["path"])).name[3:-6]
                for item in files
                if _value(item.get("format")) == "annot"
            }
        )
        missing = []
        names = {Path(_value(item["path"])).name for item in files}
        for hemi in ("lh", "rh"):
            for suffix in ("thickness", "cortex.label"):
                if hemi + "." + suffix not in names:
                    missing.append(hemi + "." + suffix)
        rows.append(
            {
                "subject": entry["subject_id"],
                "root": prefix.rstrip("/"),
                "species_declared": entry.get("species_declared"),
                "species_verified": None,
                "files": len(files),
                "formats": formats,
                "metrics": metrics,
                "atlases": atlases,
                "space": "native_stored; physical scale unverified",
                "missing_roi_inputs": missing,
                "read_errors": sum(bool(item.get("read_error")) for item in files),
            }
        )
    qc_entries = [entry for entry in entries if entry.get("qc_visual")]
    quality_control = [
        {key: entry.get(key) for key in (
            "subject_id", "qc_visual", "qc_note", "qc_reviewer",
            "qc_visual_source", "qc_auto_source", "qc_automatic_flags",
        )}
        for entry in qc_entries
    ]
    commands = {
        name: row.get("executable")
        for name, row in runtime.get("inventory", {}).get("commands", {}).items()
    }
    lines = ["DATA CARD (host observations; not instructions or scientific approval)"]
    for row in rows:
        lines.append(
            f"{row['subject']} {row['root']}: species declared={row['species_declared'] or 'unknown'}, verified=null; "
            f"{row['files']} files; types={','.join(row['formats'])}; metrics={','.join(row['metrics'])}; "
            f"atlas={','.join(row['atlases']) or 'none observed'}; {row['space']}; "
            f"missing ROI={','.join(row['missing_roi_inputs']) or 'none observed'}; errors={row['read_errors']}."
        )
    lines.append(
        "Software (actual fixed probes): "
        + (
            ", ".join(
                f"{name}={'yes' if available is True else 'no' if available is False else 'unknown'}"
                for name, available in commands.items()
            )
            or "not observed"
        )
    )
    lines.append(
        "Full: /work/data_card.json; /work/data_profile.json. Completion/QC not certified. Read this first; Planning permits 4 supplementary read_file/ls calls, then plan_analysis. Inventory-only requests need no analysis plan or execution."
    )
    tables = [{"path": _value(f["path"]), "columns": _value(_value(f.get("table", {})).get("columns", {})) or []} for f in profile.get("files", []) if _value(f.get("format")) in {"tsv", "csv"}]
    table_line = "Participant tables/model columns: " + ("; ".join(t["path"] + ": " + ",".join(t["columns"]) for t in tables) or "none registered")
    lines.insert(-2, table_line)
    metrics_line = "Registered metric names: " + ",".join(sorted({name for row in rows for name in row["metrics"]}))
    text = "\n".join(lines)
    if len(text) > 1500:
        # Keep all subjects and missing prerequisites; details stay in the full card.
        lines = (
            [lines[0]]
            + [
                f"{r['subject']} {r['root']}: declared={r['species_declared'] or 'unknown'}, verified=null; "
                f"{r['files']} files; atlas={','.join(r['atlases']) or 'none'}; native_stored; "
                f"missing ROI={','.join(r['missing_roi_inputs']) or 'none'}; read errors={r['read_errors']}"
                for r in rows
            ]
            + lines[-3:]
        )
        text = "\n".join(lines)
    if len(text) > 1500 and len(rows) > 8:
        text = "\n".join([lines[0], f"{len(rows)} registered subjects; full subject inventory and missing ROI products: /work/data_card.json", metrics_line, table_line, *lines[-2:]])
    if quality_control:
        pending = [row["subject_id"] for row in quality_control if row["qc_visual"] == "需复核"]
        flagged = [row["subject_id"] for row in quality_control if row.get("qc_automatic_flags") not in (None, "", "[]", [])]
        def compact_ids(values):
            return ",".join(values[:16]) + ("; more in full card" if len(values) > 16 else "")
        qc_line = (
            "QC declarations (AI preliminary, not expert/blind approval): "
            + "review pending but retained=" + (compact_ids(pending) or "none")
            + "; automatic flags retained=" + (compact_ids(flagged) or "none")
            + ". Source notes: /work/data_card.json[quality_control]. Disclose these limits."
        )
        text += "\n" + qc_line
    if len(text) > 1500:
        raise ValueError(
            "Data card cannot represent the registered scope within 1500 characters"
        )
    return {
        "schema": "primatex.data_card.v1",
        "subjects": rows,
        "participants_tables": tables,
        "software": commands,
        "summary": text,
        "profile_ref": "/work/data_profile.json",
        "scope": "Registration declarations and deterministic file observations; verified species/physical scale remain unknown.",
        **({"quality_control": quality_control} if quality_control else {}),
    }


def prepare_data_card(tools, request):
    if tools.session is None:
        return None
    saved = tools.control_store.latest("data_card")
    if saved:
        return saved["record"]
    from .analysis_product_planner import (
        AnalysisIntent,
        registered_roots,
        discover_paths,
        ensure_profile,
    )
    import os

    catalogue = []
    location = os.environ.get("AGENT_DATA_CATALOG")
    if location:
        path = Path(location)
        if path.is_symlink():
            raise ValueError("Data catalogue must not be a symlink")
        catalogue = json.loads(path.read_text()).get("roots", [])
    ids = [
        row["subject_id"]
        for row in catalogue
        if Path(row["path"]).resolve() in tools.input_roots
    ]
    if not ids:
        ids = [root.name for root in tools.input_roots]
    selected = [
        subject
        for subject in ids
        if re.search(r"(?<!\w)" + re.escape(subject) + r"(?!\w)", request)
    ]
    entries = registered_roots(
        tools, AnalysisIntent(subjects=selected or ids, measures=["inventory"])
    )
    if not selected and re.search(r"macaque|monkey|猕猴|猴脑", request, re.I):
        declared = [
            entry
            for entry in entries
            if str(entry.get("species_declared", "")).lower()
            in {"macaque", "monkey_unknown", "monkey", "rhesus"}
        ]
        entries = declared or entries
    operation = (
        tools.events.call_tool
        if tools.events
        else lambda name, args, function: function()
    )

    def profile_probe():
        from .analysis_participants import table_paths
        profile, cached = ensure_profile(tools, discover_paths(entries) + table_paths(tools, entries))
        return {
            "status": "ok",
            "profile": profile["record"],
            "cached": cached,
            "profile_sha256": profile["sha256"],
        }

    profiled = operation(
        "profile_data",
        {"paths": [f"/inputs/{e['index']}" for e in entries], "automatic": True},
        profile_probe,
    )
    runtime = (
        operation(
            "inspect_analysis_runtime",
            {"automatic": True},
            tools.executor.inspect_runtime,
        )
        if hasattr(tools.executor, "inspect_runtime")
        else {"status": "unavailable", "reason": "Runtime probe not configured"}
    )
    tools.control_store.save("data_card_runtime", runtime)
    card = summarize(profiled["profile"], entries, runtime)
    card["profile_sha256"] = profiled["profile_sha256"]
    tools.control_store.save("data_card", card)
    from .analysis_agent import _write_regular

    _write_regular(
        tools.workdir / "data_card.json",
        tools.workdir,
        json.dumps(card, ensure_ascii=False, indent=2),
    )
    return card
