"""Typed product-graph planning. No model calls and no preprocessing execution."""

from __future__ import annotations

import copy
import hashlib
import heapq
import json
import os
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from .analysis_control_store import canonical, digest
from .analysis_profile_worker import file_hash, value

KNOWLEDGE = Path(__file__).resolve().parent.parent / "knowledge_analysis"
PRODUCT_TYPES = {
    "surface_metric", "annotation", "cortex_label", "subject_table", "volume",
    "surface", "pial_surface", "white_surface", "registration_surface",
    "t1_volume", "t2_volume", "brainmask", "wm_segmentation", "aseg_presurf",
    "template", "tissue_priors", "bids_t1", "bids_t2", "parameter_file",
    "gm_4d", "gm_mask", "design_matrix", "contrast", "recon_complete",
    "coarse_graining_recipe", "aseg_stats", "cortical_parc_stats",
}


class AnalysisDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effect: StrictStr = Field(min_length=1, max_length=128)
    covariates: list[StrictStr] = Field(default_factory=list, max_length=16)
    reference: StrictStr | None = Field(default=None, min_length=1, max_length=128)


class AnalysisIntent(BaseModel):
    """Small intent; do not construct nested plans or constraint declarations."""

    model_config = ConfigDict(extra="forbid")
    measures: list[StrictStr] = Field(min_length=1, max_length=8)
    regions: StrictStr | list[StrictStr] = "all regions"
    comparison: Literal["describe", "group", "asymmetry", "correlation", "cross_species"] = "describe"
    species: StrictStr | None = None
    space: StrictStr | None = None
    method_id: StrictStr | None = None
    design: AnalysisDesign | None = None
    subjects: list[StrictStr] | None = Field(default=None, max_length=128)
    required_inputs: list[StrictStr] | None = Field(default=None, max_length=16)


def load_knowledge(name, tools=None):
    if tools is not None:
        from .analysis_unified_runtime import repository_for
        return repository_for(tools).document(name)
    path = KNOWLEDGE / (name + ".json")
    raw = path.read_bytes()
    expected = path.with_suffix(".sha256").read_text().split()[0]
    if path.is_symlink() or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(name + " digest mismatch")
    return json.loads(raw), expected


def uniform_cost_search(available, goals, operators):
    """Regress missing goals with uniform cost; shared stages are paid once."""
    available = frozenset(available)
    start = frozenset(goals) - available
    queue = [(0, 0, start, [])]
    best = {start: 0}
    order = 0
    while queue:
        cost, _, state, path = heapq.heappop(queue)
        if cost != best[state]:
            continue
        if not state:
            return {"cost": cost, "steps": list(reversed(path)), "execution_allowed": False}
        for step in operators:
            if not set(step["outputs"]) & state:
                continue
            next_state = ((state - set(step["outputs"])) | set(step["inputs"])) - available
            new_cost = cost + step["cost"]
            if new_cost < best.get(next_state, float("inf")):
                best[next_state] = new_cost
                order += 1
                heapq.heappush(queue, (new_cost, order, next_state, path + [step["id"]]))
    return None


def backward_plan(available, required, steps, target_space="native"):
    operators = [{**step, "inputs": [(p, step["input_space"]) for p in step["inputs"]],
                  "outputs": [(p, step["output_space"]) for p in step["outputs"]]}
                 for step in steps]
    return uniform_cost_search([tuple(item) for item in available],
                               [(item, target_space) for item in required], operators)


HEMISPHERE_PRODUCTS = {"surface", "pial_surface", "white_surface", "surface_metric",
                      "annotation", "cortex_label", "registration_surface"}


def scoped_dependency_plan(entries, files, scopes, steps, target_space):
    """Instantiate actual subject/hemisphere products; volumetric inputs are global.

    Each of the registered PrimateX stages processes both hemispheres of one
    subject. Its cost must not be counted twice or shared across subjects.
    """
    available, goals, operators = set(), set(), []
    def atoms(subject, products, space):
        return [(subject, hemi, product, space) for product in products
                for hemi in (("lh", "rh") if product in HEMISPHERE_PRODUCTS else ("global",))]
    for entry in entries:
        subject = entry["subject_id"]
        prefix = f"/inputs/{entry['index']}/"
        for item in files:
            path = value(item["path"])
            if not path.startswith(prefix):
                continue
            for product in product_types(item):
                hemi = Path(path).name[:2] if product in HEMISPHERE_PRODUCTS else "global"
                for space in ("native", "native_inputs"):
                    available.add((subject, hemi, product, space))
        for step in steps:
            operators.append({"id": subject + "::" + step["id"], "cost": step["cost"],
                              "inputs": atoms(subject, step["inputs"], step["input_space"]),
                              "outputs": atoms(subject, step["outputs"], step["output_space"])})
    for scope, products in scopes.items():
        subject, hemi = scope.rsplit("/", 1)
        for product in products:
            goals.add((subject, hemi if product in HEMISPHERE_PRODUCTS else "global", product, target_space))
    result = uniform_cost_search(available, goals, operators)
    if result is None:
        return None
    selected = [{"subject": key.split("::", 1)[0], "step": key.split("::", 1)[1]} for key in result["steps"]]
    return {**result, "steps": [item["step"] for item in selected], "scoped_steps": selected,
            "by_scope": [{"scope": scope, "steps": [item["step"] for item in selected
                           if item["subject"] == scope.rsplit("/", 1)[0]]} for scope in scopes],
            "cost_policy": "Unique subject-stage executions; shared hemispheres counted once",
            "scope": "Minimum in this abstract product/space graph; scientific and software prerequisites still require verification"}


def validate_intent(raw):
    try:
        intent = raw if isinstance(raw, AnalysisIntent) else AnalysisIntent.model_validate(raw)
    except ValidationError as exc:
        errors = []
        for item in exc.errors(include_input=False, include_url=False):
            location = ".".join(str(part) for part in item["loc"])
            message = "regions must be a string or list of strings" if location.startswith("regions") else item["msg"]
            errors.append({"field": location, "message": message})
        return None, {"status": "error", "reason": "Invalid analysis intent", "field_errors": errors}
    for key, field in intent.model_dump().items():
        strings = field if isinstance(field, list) else [field]
        if any(isinstance(s, str) and (not s.strip() or len(s) > 500) for s in strings):
            return None, {"status": "error", "field_errors": [{"field": key, "message": "Use nonempty strings of at most 500 characters"}]}
    if intent.design:
        columns = [intent.design.effect, *intent.design.covariates]
        if len(columns) != len(set(columns)) or any(not c.strip() or len(c)>128 for c in columns):
            return None, {"status": "error", "field_errors": [{"field": "design.covariates", "message": "Use distinct nonempty design column names of at most 128 characters"}]}
    if intent.method_id and intent.method_id.startswith("self:"):
        if not intent.required_inputs or not set(intent.required_inputs) <= PRODUCT_TYPES:
            return None, {"status": "error", "field_errors": [{"field": "required_inputs", "message": "A self: method must list registered product types"}]}
    return intent, None


def normal_measure(name):
    word = re.sub(r"[^a-z0-9]", "", name.lower())
    return {
        "corticalthickness": "thickness", "brainvolumemm3": "brainvolume",
        "totalareamm2": "totalarea", "meanthicknessmm": "meanthickness",
        "globalmetrics": "globalmorphometry", "convexhullratio": "gyrification",
        "hullratio": "gyrification", "curvature": "curv", "sulcaldepth": "sulc",
        "localgyrificationindex": "lgi", "localgyrification": "lgi",
        "gyrificationindex": "gyrification", "surfacearea": "area",
    }.get(word, word)


def registered_roots(tools, intent):
    catalogue = []
    location = os.environ.get("AGENT_DATA_CATALOG")
    if location:
        path = Path(location)
        if path.is_symlink():
            raise ValueError("Data catalogue must not be a symlink")
        catalogue = json.loads(path.read_text())["roots"]
    entries = []
    for index, root in enumerate(tools.input_roots):
        if index in {row["index"] for row in getattr(tools, "participants_tables", [])}:
            continue
        matches = [row for row in catalogue if Path(row["path"]).resolve() == root]
        entry = matches[0] if matches else {"subject_id": root.name, "species_declared": None, "source": "approved root registration; species unavailable"}
        entries.append({**entry, "index": index, "root": root})
    if intent.subjects:
        entries = [r for r in entries if r["subject_id"] in intent.subjects]
        if {r["subject_id"] for r in entries} != set(intent.subjects):
            raise ValueError("subjects must identify approved registered subjects")
    elif intent.species:
        requested = intent.species.lower()
        def matches(row):
            declared = str(row.get("species_declared") or "").lower()
            if requested in {"macaque", "monkey", "monkey_unknown", "nonhuman primate", "rhesus"}:
                return declared in {"monkey_unknown", "macaque", "rhesus"}
            return declared == requested
        entries = [row for row in entries if matches(row)]
    elif len(entries) > 1:
        raise ValueError("subjects or declared species is required when multiple data roots are registered")
    if not entries:
        raise ValueError("No approved root matches subjects/species; no filename-based species inference is permitted")
    return entries


def discover_paths(entries):
    paths = []
    for entry in entries:
        root, index = entry["root"], entry["index"]
        for directory in ("surf", "label", "mri", "stats"):
            folder = root / directory
            if not folder.is_dir():
                continue
            from .analysis_input_links import resolve_input
            try:
                resolve_input(folder, root)
            except (ValueError, OSError, RuntimeError):
                continue
            for path in sorted(folder.iterdir()):
                if not path.is_file():
                    continue
                from .analysis_input_links import resolve_input
                try:
                    resolve_input(path, root)
                except (ValueError, OSError, RuntimeError):
                    continue
                if directory == "surf" and not re.fullmatch(r"[lr]h\.(white|pial|sphere\.reg|thickness|curv|sulc|area|volume|lgi)", path.name):
                    continue
                if directory == "label" and not (path.suffix == ".annot" or path.name in {"lh.cortex.label", "rh.cortex.label"}):
                    continue
                if directory == "mri" and path.name not in {"orig.mgz", "T1.mgz", "brainmask.mgz", "wm.mgz", "aseg.presurf.mgz"}:
                    continue
                if directory == "stats" and not (path.name == "aseg.stats" or re.fullmatch(r"[lr]h\.aparc.*\.stats", path.name)):
                    continue
                paths.append(f"/inputs/{index}/" + path.relative_to(root).as_posix())
        if not (root / "surf").exists():
            for path in sorted(root.iterdir()):
                if path.is_file() and not path.is_symlink() and path.name.endswith((".nii", ".nii.gz", ".mgz", ".tsv")):
                    paths.append(f"/inputs/{index}/" + path.name)
    if not 1 <= len(paths) <= 4096:
        raise ValueError("Approved product inventory requires 1..4096 files; no silent truncation")
    return paths


def ensure_profile(tools, paths):
    from .analysis_data_profile import profile_data
    stamps = []
    for path in paths:
        target = tools.resolve(path)
        stamps.append([path, str(target), *file_hash(target)])
        scripts = target.parent.parent / "scripts"
        for name in ("recon-all.done", "recon-all.log", "recon-surf.done", "recon-surf.log"):
            adjacent = scripts / name
            if adjacent.is_file() and not adjacent.is_symlink():
                stamps.append([str(adjacent), *file_hash(adjacent)])
    key = digest({"inputs": stamps, "worker_sha256": hashlib.sha256(Path(__file__).with_name("analysis_profile_worker.py").read_bytes()).hexdigest()})
    latest = tools.control_store.latest("planner_profile_cache")
    profile = tools.control_store.latest("data_profile")
    if latest and profile and latest["record"]["input_fingerprint"] == key and latest["record"]["profile_sha256"] == profile["sha256"]:
        return profile, True
    result = profile_data(tools, paths)
    if result.get("status") != "ok":
        raise ValueError("Deterministic product profiling failed: " + str(result.get("reason")))
    profile = tools.control_store.latest("data_profile")
    tools.control_store.save("planner_profile_cache", {"input_fingerprint": key, "profile_sha256": profile["sha256"]})
    return profile, False


def product_types(item):
    kind, path = value(item["format"]), Path(value(item["path"]))
    found = set()
    if kind in {"tsv", "csv"}:
        found.add("subject_table")
    if kind == "surface":
        found.add("surface")
        if path.name.endswith(".pial"):
            found.add("pial_surface")
        if path.name.endswith(".white"):
            found.add("white_surface")
        if path.name.endswith(".sphere.reg"):
            found.add("registration_surface")
    elif kind == "surface_metric":
        found.add("surface_metric")
    elif kind == "annot":
        found.add("annotation")
    elif kind == "label" and path.name.endswith(".cortex.label"):
        found.add("cortex_label")
    elif kind in {"nifti", "mgz"}:
        found.add("volume")
        if path.name in {"orig.mgz", "T1.mgz"} or "T1w" in path.name:
            found.add("t1_volume")
        if "T2w" in path.name:
            found.add("t2_volume")
        if path.name == "brainmask.mgz":
            found.add("brainmask")
        if path.name == "wm.mgz":
            found.add("wm_segmentation")
        if path.name == "aseg.presurf.mgz":
            found.add("aseg_presurf")
    if kind == "stats":
        if path.name == "aseg.stats":
            found.add("aseg_stats")
        elif re.fullmatch(r"[lr]h\.aparc.*\.stats", path.name):
            found.add("cortical_parc_stats")
    if value(item.get("subject")):
        found.add("subject_table")
    recon = value(item.get("recon"))
    if recon and value(recon["done"]) is True and value(recon["fatal_count"]) == 0:
        found.add("recon_complete")
    return found


def resolve_regions(names, keys, counts, regions, domain):
    tokens = [regions] if isinstance(regions, str) else regions
    tokens = [t.lower().strip() for t in tokens]
    all_regions = all(t in {"all", "all regions", "whole cortex", "cortex", "global", "both hemispheres"} for t in tokens)
    special = lambda n: re.sub(r"[^a-z]", "", n.lower()) in {"unknown", "medialwall", "corpuscallosum"}
    selected, sources, unmatched = [], [], []
    graph = domain.get("nodes", [])
    for index, name in enumerate(names):
        key = keys[index]
        if special(name) or counts.get(str(key), 0) <= 0:
            continue
        matching = [node for node in graph if node.get("type") == "LabelDefinition" and node.get("name") in {name, "ctx-lh-" + name, "ctx-rh-" + name}]
        if all_regions or name.lower() in tokens:
            selected.append({"key": key, "name": name})
            sources.extend({"node_id": node["id"], "source": node.get("evidence", [])} for node in matching[:1])
    if not all_regions:
        unmatched = [token for token in tokens if token not in {row["name"].lower() for row in selected}]
    return selected, sources, unmatched


def _candidate(tools, spec, method, entries, files, atlas_name, intent, domain, profile):
    if method["id"] == "method:v15:global_morphometry":
        from .analysis_global_method import candidate
        return candidate(tools, spec, method, entries, files, intent, profile)
    chosen, bindings, labels, mapping = [], [], {}, []
    missing = set()
    missing_scopes = {}
    measures = [normal_measure(m) for m in intent.measures]
    for entry in entries:
        prefix = f"/inputs/{entry['index']}/"
        group = [f for f in files if value(f["path"]).startswith(prefix)]
        for hemi in ("lh", "rh"):
            members = [f for f in group if Path(value(f["path"])).name.startswith(hemi + ".")]
            by_type = {kind: [f for f in members if kind in product_types(f)] for kind in PRODUCT_TYPES}
            for need in spec["required_products"]:
                possible = by_type[need] if need in {"surface", "pial_surface", "white_surface", "surface_metric", "annotation", "cortex_label", "registration_surface"} else [f for f in group if need in product_types(f)]
                if need == "subject_table":
                    possible = [f for f in files if value(f["format"]) in {"tsv", "csv"}]
                if need == "surface_metric":
                    possible = [f for f in possible if Path(value(f["path"])).name.split(".")[-1] in measures]
                if need == "annotation":
                    possible = [f for f in possible if Path(value(f["path"])).name == f"{hemi}.{atlas_name}.annot"]
                if need == "surface":
                    possible.sort(key=lambda f: (not value(f["path"]).endswith(".white"), value(f["path"])))
                if not possible:
                    missing.add(need)
                    missing_scopes.setdefault(entry["subject_id"] + "/" + hemi, []).append(need)
                else:
                    chosen.extend(possible if need == "surface_metric" else possible[:1])
            if spec["needs_parcellation"] and by_type["annotation"]:
                ann = next((f for f in by_type["annotation"] if value(f["path"]).endswith(f".{atlas_name}.annot")), None)
                surf = next((f for f in chosen if value(f["path"]).startswith(prefix) and Path(value(f["path"])).name == hemi + ".white"), None)
                reg = by_type["registration_surface"][:1]
                if ann:
                    detail = value(ann["label"])
                    keys = value(detail.get("label_keys")) or list(range(len(value(detail["label_names"]))))
                    counts = value(detail.get("cortex_retained_label_counts")) or value(detail.get("label_vertex_counts")) or {}
                    from .analysis_lobar_mapping import resolve_lobes
                    requested, lobe_evidence, lobe_error = resolve_lobes(entry, atlas_name, intent.regions, value(detail["label_names"]), tools=tools)
                    selected, evidence, unresolved = resolve_regions(value(detail["label_names"]), keys, counts, requested, domain)
                    evidence.extend(lobe_evidence)
                    if lobe_error:
                        missing.add("parcellation_mapping:" + lobe_error)
                        selected = []
                    if unresolved or not selected:
                        missing.add("resolved_regions:" + ",".join(unresolved))
                    labels[entry["subject_id"] + "/" + hemi] = {"annotation": value(ann["path"]), "labels": selected, "exclude_keys": [-1], "exclude_names": ["unknown", "medialwall", "corpuscallosum"], "cortex_label": prefix + "label/" + hemi + ".cortex.label"}
                    mapping.extend(evidence)
                    if surf and reg:
                        bindings.append({"label": value(ann["path"]), "surface": value(surf["path"]), "mesh_origin": "same approved subject native derivative bundle; anatomical provenance unverified", "space": "native_stored", "registration_ref": value(reg[0]["path"])})
    chosen = list({value(f["path"]): f for f in chosen}.values())
    atlas = {"name": atlas_name or "not applicable", "version": "input annotation fingerprint; acquisition release unknown" if atlas_name else None, "space": "native_stored", "hemisphere_rule": "separate lh/rh; preserve native vertex IDs", "applicable": bool(atlas_name), "reason": None if atlas_name else "Method operates on whole supplied surfaces without a parcellation", "exclude_labels": [-1, "unknown", "medialwall", "corpuscallosum"], "mesh_bindings": bindings}
    notice = ["Species is user/registration-declared only; not independently verified", "Stored coordinates/values; no verified acquisition-scale or expert anatomical-QC claim"]
    if method["id"].endswith("global_convex_hull_gyrification"):
        notice.append("Global full-pial-area / same-surface 3D convex-hull area is a descriptive alternative, not local gyrification index (lGI)")
    context = {"question": "Describe requested stored products with " + method["name"], "data": {"files": [value(f["path"]) for f in chosen], "subjects": [e["subject_id"] for e in entries], "profile_sha256": profile["sha256"], "profile_ref": f"data_profile.v{profile['version']:06d}.json", "species_declared": intent.species, "species_verified": None}, "atlas": atlas, "method": {"method_id": method["id"], "name": method["name"], "reason": "Candidate for declared measures and comparison; selected by Agent at commitment"}, "outputs": ["summary.csv", "summary.json", "report.md"], "code_path": "/work/analysis.py", "analysis_scope": {"inference": intent.comparison in {"group", "correlation"}, "scale_policy": "dimensionless_per_input" if method["id"].endswith("global_convex_hull_gyrification") else "within_input_only", "comparison": intent.comparison, "labels": labels, "notices": notice}}
    if method["id"] == "method:v14:group_regional_glm":
        context["outputs"] = ["regional_values.csv", "group_results.csv", "summary.json", "report.md"]
    if atlas_name:
        from .analysis_atlas_identity import identify
        identity = identify(atlas_name)
        if identity:
            context["atlas"].update(canonical_name=identity["canonical_name"],
                                    official_name=identity["official_name"],
                                    naming_source=identity["source_url"], filename_stem=atlas_name)
    if method["id"].startswith("self:"):
        context["method"]["required_software"] = []
    return context, sorted(missing), mapping, missing_scopes


def method_evidence_view(graph, method):
    from .analysis_evidence import evidence_id
    method_id = method["id"]
    view = {"method_id": method_id, "name": method["name"]}
    if method_id.startswith("self:"):
        return view
    card = graph.read(method_id)
    view["evidence_id"] = evidence_id("method", method_id)
    view["source_reads"] = [{"id": evidence_id("source_text", "METHOD_SOURCE_" + source["source_id"]),
                             "source_url": source["url"]}
                            for source in card.get("source_evidence", [])]
    return view


def plan_analysis(tools, raw):
    intent, error = validate_intent(raw)
    if error:
        return error
    entries = registered_roots(tools, intent)
    from .analysis_participants import table_paths
    paths = discover_paths(entries) + table_paths(tools, entries)
    profile, cached = ensure_profile(tools, paths)
    design_scope = None
    if intent.comparison in {"group", "correlation"}:
        from .analysis_group_design import bind_design
        design_scope, design_error = bind_design(tools, intent, entries, profile["record"]["files"])
        if design_error:
            tools.control_store.save("planning_result", design_error)
            return design_error
    requirements, req_sha = load_knowledge("method_requirements", tools)
    dependencies, dep_sha = load_knowledge("pipeline_dependencies", tools)
    graph = tools._method_graph()
    from .analysis_unified_runtime import repository_for
    repository = repository_for(tools)
    try:
        domain, domain_sha = repository.document("domain_graph")
    except ValueError:
        domain, domain_sha = {"nodes": []}, None
    from .analysis_product_instances import import_profile
    registry = [{**{key: val for key, val in entry.items() if key != "root"}, "path": str(entry["root"]), "input_index": entry["index"]} for entry in entries]
    import_profile(repository, profile["record"], registry)
    files = [f for f in profile["record"]["files"] if not f.get("read_error")]
    requested_atlas = None
    resolution = None
    known_atlases = {Path(value(f["path"])).name[3:-6] for f in files
                     if value(f["format"]) == "annot"}
    actual_label_names = {name.casefold() for f in files if value(f["format"]) == "annot"
                          for name in (value(value(f.get("label", {})).get("label_names")) or [])}
    if isinstance(intent.regions, str):
        matching = [name for name in known_atlases if name.casefold() == intent.regions.casefold().strip()]
        if matching and intent.regions.casefold().strip() not in actual_label_names:
            requested_atlas = matching[0]
            resolution = {"original_regions": intent.regions, "effective_regions": "all regions",
                          "atlas": requested_atlas, "basis": "Exact registered annotation name, not an inferred anatomical group",
                          "source_paths": [value(f["path"]) for f in files
                                           if Path(value(f["path"])).name.endswith('.'+requested_atlas+'.annot')]}
            intent = intent.model_copy(update={"regions": "all regions"})
    from .analysis_atlas_identity import requested as requested_family, identify
    requested_name = requested_family(intent.regions, getattr(tools, "task_request", ""))
    matching_families = [name for name in sorted(known_atlases)
                         if identify(name) and identify(name)["canonical_name"] == requested_name]
    missing_atlas = requested_name and not matching_families
    if requested_name and matching_families:
        requested_atlas = matching_families[0]
        resolution = {"original_regions": intent.regions, "effective_regions": "all regions",
                      "atlas": requested_atlas, "canonical_name": requested_name,
                      "basis": "Explicit requested atlas; exact source-backed filename mapping"}
        intent = intent.model_copy(update={"regions": "all regions"})
    if missing_atlas:
        available = sorted({identify(name)["canonical_name"] for name in known_atlases if identify(name)})
        reason = "Missing " + requested_name + "; available " + (", ".join(available) or "no registered named parcellation")
        row = {"constraint_id": "requested_atlas_present", "severity": "hard", "verdict": "block",
               "tool_observed": {"reason": reason, "requested": requested_name, "available": available,
                                 "evidence_ref": "data_profile.v%06d.json" % profile["version"]},
               "source": [{"path": "knowledge_analysis/atlas_identifiers_r13.json"}]}
        check = {"method_id": "data:requested_atlas", "rows": [row],
                 "summary": {"pass": 0, "warn": 0, "block": 1}, "unmapped_conditions": []}
        saved_check = tools.control_store.save("constraints", check)
        result = {"status": "blocked", "candidates": [], "needs_preprocessing": [],
                  "infeasible": [{"reason": reason, "blocked_constraints": [row]}],
                  "requested_atlas": requested_name, "available_atlases": available,
                  "constraints_sha256": saved_check["sha256"],
                  "next_steps": ["Ask the user to select an available atlas or provide the requested atlas; do not substitute"]}
        tools.control_store.save("planning_result", result)
        return result
    measures = {normal_measure(m) for m in intent.measures}
    specs = [s for s in requirements["methods"] if s["method_id"] != "self:*" and measures <= set(s["measures"]) and intent.comparison in s["comparisons"]]
    if not (measures & {"globalmorphometry", "brainvolume", "etiv", "totalarea", "meanthickness"}):
        specs = [s for s in specs if s["method_id"] != "method:v15:global_morphometry"]
    region_tokens = [intent.regions] if isinstance(intent.regions, str) else intent.regions
    if any(t.lower().strip() not in {"global", "whole cortex", "cortex", "both hemispheres"} for t in region_tokens):
        specs = [s for s in specs if not s["method_id"].endswith("existing_curvature_sulc_profile")]
    if intent.method_id and not intent.method_id.startswith("self:"):
        specs = [s for s in requirements["methods"] if s["method_id"] == intent.method_id or ("lgi" in measures and s["method_id"].endswith("global_convex_hull_gyrification"))]
    if intent.method_id and intent.method_id.startswith("self:"):
        specs = [{"method_id": intent.method_id, "required_products": intent.required_inputs, "needs_parcellation": False, "execution_scope": "supplied_derivatives", "source": [{"type": "project_policy", "note": "Explicit self-written method; scientific applicability unverified"}]}]
    output = {"status": "ok", "candidates": [], "needs_preprocessing": [], "infeasible": [], "profile_cached": cached, "profile_ref": f"data_profile.v{profile['version']:06d}.json", "method_requirements_sha256": req_sha, "pipeline_dependencies_sha256": dep_sha, "domain_graph_sha256": domain_sha, "input_file_count": len(files)}
    output["intent_resolution"] = resolution
    from .analysis_constraints import compile_constraints
    for spec in specs:
        method = graph.read(spec["method_id"])["method"] if not spec["method_id"].startswith("self:") else {"id": spec["method_id"], "name": spec["method_id"], "conditions": [], "inputs": []}
        if intent.comparison == "cross_species" and spec["needs_parcellation"]:
            output["infeasible"].append({"method": method_evidence_view(graph, method),
                                         "atlas": {"name": "unresolved correspondence", "applicable": True},
                                         "reason": "Verified cross-species correspondence is unavailable; shared label names do not establish homology",
                                         "conditions": {"pass": 0, "warn": 0, "block": 1}})
            continue
        atlases = sorted({Path(value(f["path"])).name[3:-6] for f in files if value(f["format"]) == "annot"}) if spec["needs_parcellation"] else [None]
        if requested_atlas and spec["needs_parcellation"]:
            atlases = [name for name in atlases if name == requested_atlas]
        for atlas_name in atlases or ["unavailable"]:
            context, missing, mapping, missing_scopes = _candidate(tools, spec, method, entries, files, atlas_name, intent, domain, profile)
            if design_scope:
                context["analysis_scope"].update(copy.deepcopy(design_scope))
            if resolution:
                context["analysis_scope"]["intent_resolution"] = resolution
            from .analysis_operations import suggested_operations
            operations = suggested_operations(context)
            item = {"operations": operations, "method": method_evidence_view(graph, method), "atlas": context["atlas"], "space": intent.space or "native", "missing_products": missing}
            if intent.space and intent.space not in {"native", "native_stored", "stored"}:
                missing = sorted(set(missing) | set(spec["required_products"]))
            constraints = compile_constraints(tools, method["id"], "group_inference" if intent.comparison in {"group", "correlation"} else "descriptive", context, product_contract=spec)
            item["conditions"] = constraints["summary"]
            item["blocked_constraints"] = [row for row in constraints["rows"] if row["verdict"] == "block"]
            if item["blocked_constraints"]:
                tools.control_store.save("planning_failure", {
                    "constraints_sha256": constraints["constraints_sha256"],
                    "plan_context": context,
                    "method_id": method["id"],
                    "reason": "Observed failed candidate prerequisites",
                })
            unrepairable = [row for row in item["blocked_constraints"]
                            if row["constraint_id"] not in {"recon_complete", "mesh_label_match", "product_metric_mesh_identity"}]
            if unrepairable or (item["blocked_constraints"] and not missing):
                item["reason"] = "; ".join(row["constraint_id"] + ": " + str(row["tool_observed"].get("reason", "failed observed prerequisite")) for row in item["blocked_constraints"])
                missing_commands = [c["command"] for row in item["blocked_constraints"] for c in row["tool_observed"].get("commands", []) if not c.get("executable")]
                if missing_commands:
                    item["reason"] = "Missing software: " + ", ".join("MATLAB" if c == "matlab" else c for c in missing_commands)
                output["infeasible"].append(item)
                continue
            if any(part.startswith("parcellation_mapping:") for part in missing):
                item["reason"] = "; ".join(part.split(":",1)[1] for part in missing if part.startswith("parcellation_mapping:"))
                output["infeasible"].append(item)
                continue
            if missing or spec["execution_scope"] == "full_processing":
                scopes = missing_scopes or {entry["subject_id"] + "/" + hemi: missing or ["complete_analysis_recipe"]
                                           for entry in entries for hemi in ("lh", "rh")}
                path = scoped_dependency_plan(entries, files, scopes, dependencies["steps"], intent.space or "native")
                unresolved = [part.split(":",1)[1] for part in missing if part.startswith("resolved_regions:")]
                item["reason"] = ("Unresolved region labels: " + "; ".join(unresolved)
                                  + ". Use actual annotation label names or 'all regions'."
                                  if unresolved else "Missing or unsupported product/space/complete method recipe")
                if path:
                    item["preprocessing_plan"] = path
                    output["needs_preprocessing"].append(item)
                else:
                    output["infeasible"].append(item)
                continue
            candidate_id = "candidate_" + digest({"intent": intent.model_dump(), "plan": context, "requirements": req_sha})[:24]
            record = {"candidate_id": candidate_id, "intent": intent.model_dump(), "plan": context, "product_contract": spec, "mapping_evidence": mapping, "profile_sha256": profile["sha256"], "method_requirements_sha256": req_sha, "pipeline_dependencies_sha256": dep_sha, "domain_graph_sha256": domain_sha, "condition_snapshot": constraints, "operations": operations}
            tools.control_store.save(candidate_id, record)
            summary = {"candidate_id": candidate_id, "method": item["method"], "atlas": {k: context["atlas"][k] for k in ["name", "version", "space", "applicable", "reason"]}, "space": "native_stored", "file_count": len(context["data"]["files"]), "subjects": context["data"]["subjects"], "label_counts": {key: len(group["labels"]) for key, group in context["analysis_scope"]["labels"].items()}, "conditions": constraints["summary"], "must_disclose": context["analysis_scope"]["notices"], "protected_ref": candidate_id, "mapping_source_count": len(mapping)}
            summary["operations"] = operations
            from .analysis_asymmetry_contract import applies as asymmetry_applies, definition as asymmetry_definition
            if asymmetry_applies(context):
                summary["asymmetry_contract"] = asymmetry_definition()
            output["candidates"].append(summary)
    if not specs:
        output["infeasible"].append({"reason": "No registered method matches the requested measures and comparison"})
    saved = tools.control_store.save("planning_result", output)
    output["protected_ref"] = f"planning_result.v{saved['version']:06d}.json"
    # Large failure observations remain host-owned; expose a bounded explanation.
    for row in output["infeasible"]:
        row["atlas"] = {k: row["atlas"].get(k) for k in ("name", "applicable")} if "atlas" in row else None
        row["blocked_constraints"] = [{"constraint_id": r["constraint_id"], "severity": r["severity"], "verdict": r["verdict"], "reason": r["tool_observed"].get("reason")} for r in row.get("blocked_constraints", [])]
    return output


def commit_candidate(tools, candidate_id, rationale, code_path, commitment=None):
    from .analysis_constraints import compile_constraints
    from .analysis_plans import commit_plan
    if not isinstance(candidate_id, str) or not re.fullmatch(r"candidate_[a-f0-9]{24}", candidate_id):
        raise ValueError("candidate_id must identify a protected feasible candidate")
    if not isinstance(rationale, str) or not 1 <= len(rationale.strip()) <= 1200:
        raise ValueError("rationale must be one or two short sentences")
    saved = tools.control_store.latest(candidate_id)
    profile = tools.control_store.latest("data_profile")
    if not saved or not profile or saved["record"]["profile_sha256"] != profile["sha256"]:
        return {"status": "blocked", "reason": "Candidate missing or profile changed; call plan_analysis again"}
    record = saved["record"]
    if (record["method_requirements_sha256"] != load_knowledge("method_requirements", tools)[1]
            or record["pipeline_dependencies_sha256"] != load_knowledge("pipeline_dependencies", tools)[1]):
        return {"status": "blocked", "reason": "Requirements changed; call plan_analysis again"}
    if not isinstance(code_path, str) or len(json.dumps(code_path)) > 240:
        raise ValueError("code_path must be a bounded /work Python path")
    original_code_path = code_path
    from .analysis_plans import _work_path
    if not code_path.startswith("/"):
        code_path = "/work/" + code_path
    code_path = _work_path(code_path)
    context = copy.deepcopy(record["plan"])
    context["code_path"] = code_path
    context["candidate_id"] = candidate_id
    context["selection_rationale"] = rationale
    context["revision_reason"] = rationale
    context["analysis_scope"]["mapping_evidence_ref"] = candidate_id
    from .analysis_crossspecies import enabled as cross_enabled, validate_commitment
    if cross_enabled(tools):
        checked_commitment = validate_commitment(commitment, context)
        context.update(checked_commitment)
        context["analysis_scope"]["commitment"] = checked_commitment

    from .analysis_operations import execution_bundle
    bundle = execution_bundle(context)
    if cross_enabled(tools):
        bundle["commitment"] = checked_commitment
    context["analysis_scope"]["operations_sha256"] = bundle["operations"]["library"]["sha256"]
    # Bind operations to the sealed core before the final, authoritative checks.
    checks = compile_constraints(tools, context["method"]["method_id"], "group_inference" if context["analysis_scope"]["inference"] else "descriptive", context, product_contract=record["product_contract"])
    context["constraints"] = {"version": checks["version"], "sha256": checks["constraints_sha256"]}
    # Reject an oversized execution card before sealing, while replanning tools
    # are still available. Never commit a plan the model cannot receive intact.
    previous_plan = tools.control_store.latest("plan")
    next_version = previous_plan["version"] + 1 if previous_plan else 1
    draft_bundle = {**bundle, "label_sets_ref": {"path": f"/work/label_sets.v{next_version:06d}.json"},
                    "bundle_ref": f"/work/execution_bundle.v{next_version:06d}.json"}
    from .analysis_execution_card import execution_card
    execution_card({"plan": context, "execution_bundle": draft_bundle, "version": next_version})
    result = commit_plan(tools, context)
    if result.get("status") == "committed":
        label_path = f"/work/label_sets.v{result['version']:06d}.json"
        raw = canonical(bundle["label_sets"])
        target = tools.resolve(label_path, writable=True)
        if target.exists():
            raise ValueError("Refuse to overwrite a versioned label set")
        target.write_bytes(raw)
        bundle["label_sets_ref"] = {"path": label_path, "sha256": hashlib.sha256(raw).hexdigest()}
        if context["method"]["method_id"] == "method:v14:group_regional_glm":
            from .analysis_group_manifest import write_manifest
            bundle["inputs_manifest"] = write_manifest(tools, context, bundle)
        bundle["must_disclose"] += result["must_disclose"]
        bundle_path = f"/work/execution_bundle.v{result['version']:06d}.json"
        bundle["bundle_ref"] = bundle_path
        bundle_copy = {key: val for key, val in bundle.items() if key != "label_sets"}
        from .analysis_agent import _write_regular
        _write_regular(tools.resolve(bundle_path, writable=True), tools.workdir,
                       json.dumps(bundle_copy, ensure_ascii=False, indent=2))
        tools.control_store.save("execution_bundle", {"plan_sha256": result["plan_sha256"], **bundle})
        result["execution_bundle"] = bundle
        if original_code_path != code_path:
            result["path_normalization"] = {"original": original_code_path, "code_path": code_path,
                                            "notice": "Relative code_path resolved beneath /work"}
    if result.get("status") == "committed" and not context["method"]["method_id"].startswith("self:"):
        result["method_evidence"] = method_evidence_view(tools._method_graph(), {"id": context["method"]["method_id"], "name": context["method"]["name"]})
    return result
