"""Deterministic header/label probe run by trusted code in the image sandbox.

Importing this module does not import nibabel or read participant data. Tests
can construct synthetic headers; production executes main via a frozen source.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re


def field(value, path, method, reason=None):
    result = {"value": value, "source": {"path": str(path), "method": method}}
    if reason:
        result["reason"] = str(reason)[:500]
    return result


def value(item):
    return item.get("value") if isinstance(item, dict) else None


def file_format(path):
    name = path.name.lower()
    for suffix, kind in (
        (".label.gii", "label.gii"),
        (".shape.gii", "shape.gii"),
        (".nii.gz", "nifti"),
        (".nii", "nifti"),
        (".mgz", "mgz"),
        (".mgh", "mgz"),
        (".annot", "annot"),
        (".stats", "stats"),
        (".tsv", "tsv"),
        (".label", "label"),
    ):
        if name.endswith(suffix):
            return kind
    if name.split(".")[-1] in {"curv", "thickness", "sulc", "area", "volume", "lgi"}:
        return "surface_metric"
    try:
        with path.open("rb") as stream:
            magic = int.from_bytes(stream.read(3), "big")
        if magic in (16777213, 16777214, 16777215):
            return "surface"
    except OSError:
        pass
    if name.endswith(".surf.gii"):
        return "surface"
    return "unknown"


def file_hash(path):
    size = path.stat().st_size
    with path.open("rb") as stream:
        if size <= 64 * 1024 * 1024:
            h = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
            return h.hexdigest(), "sha256_full_file"
        raw = stream.read(1024 * 1024)
    return (
        hashlib.sha256(raw + str(size).encode()).hexdigest(),
        "sha256_first_1MiB_plus_decimal_file_size_not_full_file",
    )


def hemisphere(path):
    name = path.name.lower()
    hemi = (
        "left"
        if name.startswith("lh.")
        else "right" if name.startswith("rh.") else None
    )
    return field(
        hemi,
        path,
        "FreeSurfer filename prefix",
        None if hemi else "Hemisphere not declared by recognized filename",
    )


def profile_file(path):
    kind = file_format(path)
    item = {
        "path": field(str(path), path, "approved sandbox mapping"),
        "format": field(kind, path, "recognized suffix or FreeSurfer geometry magic"),
        "sha256": field(None, path, "not read", "File unreadable"),
        "volume": field(None, path, "format dispatch", "Not a volume"),
        "surface": field(None, path, "format dispatch", "Not a surface"),
        "metric": field(None, path, "format dispatch", "Not a per-vertex metric"),
        "label": field(None, path, "format dispatch", "Not a label/annotation"),
        "recon": field(
            None,
            path,
            "adjacent scripts directory",
            "No reconstruction directory identified",
        ),
        "subject": field(
            None,
            path,
            "explicit table metadata only",
            "No trusted subject mapping supplied",
        ),
    }
    try:
        resolved = path.resolve(strict=True)
        # The sandbox exposes one registered subject per /inputs/N root.
        if str(path).startswith("/inputs/"):
            root = Path(*path.parts[:3])
            if not resolved.is_relative_to(root):
                raise ValueError("Input link escapes registered subject root")
        if path.is_symlink():
            item["link"] = field({"original": str(path), "target": str(path.readlink()),
                                  "resolved": str(resolved)}, path, "subject-local symlink resolution")
        sha, method = file_hash(path)
        item["sha256"] = field(sha, path, method)
        item["size_bytes"] = field(path.stat().st_size, path, "stat.st_size")
        if kind in (
            "nifti",
            "mgz",
            "surface",
            "annot",
            "label.gii",
            "shape.gii",
            "label",
            "surface_metric",
        ):
            import nibabel as nib
            import numpy as np
        if kind in ("nifti", "mgz"):
            image = nib.load(str(path), mmap=True)
            units = image.header.get_xyzt_units()[0] if kind == "nifti" else "mm"
            factors = {"mm": 1.0, "meter": 1000.0, "micron": 0.001}
            factor = factors.get(units)
            zooms = [float(z) for z in image.header.get_zooms()[:3]]
            qform = sform = None
            conflict = None
            if kind == "nifti":
                q, qc = image.get_qform(coded=True)
                s, sc = image.get_sform(coded=True)
                qform, sform = int(qc), int(sc)
                if q is not None and s is not None:
                    conflict = not bool(np.allclose(q, s, rtol=1e-5, atol=1e-5))
            details = {
                "shape": field(
                    [int(size) for size in image.shape],
                    path,
                    "nibabel image.shape; header only",
                ),
                "voxel_size_mm": field(
                    [z * factor for z in zooms] if factor else None,
                    path,
                    "header.get_zooms and declared unit conversion",
                    None if factor else "Header spatial units unknown",
                ),
                "stored_zooms": field(zooms, path, "header.get_zooms"),
                "units": field(
                    units,
                    path,
                    "NIfTI header or MGH format millimetre convention; not acquisition verification",
                ),
                "affine": field(
                    image.affine.tolist(), path, "nibabel selected affine; no rounding"
                ),
                "qform_code": field(
                    qform,
                    path,
                    "get_qform(coded=True)",
                    "MGH has no NIfTI qform" if kind == "mgz" else None,
                ),
                "sform_code": field(
                    sform,
                    path,
                    "get_sform(coded=True)",
                    "MGH has no NIfTI sform" if kind == "mgz" else None,
                ),
                "qform_sform_conflict": field(
                    conflict,
                    path,
                    "compare coded forms with rtol/atol 1e-5",
                    (
                        None
                        if conflict is not None
                        else "Two coded transforms unavailable"
                    ),
                ),
            }
            item["volume"] = field(
                details, path, "nibabel header only; image array not loaded"
            )
        elif kind == "surface_metric":
            values = nib.freesurfer.read_morph_data(str(path))
            item["metric"] = field({
                "vertex_count": field(int(values.size), path, "read_morph_data vector length"),
                "ndim": field(int(values.ndim), path, "actual read_morph_data array.ndim"),
                "measure": field(path.name.split(".")[-1], path, "filename convention; not algorithm provenance"),
                "finite_count": field(int(np.isfinite(values).sum()), path, "actual stored vector finite values"),
                "units": field(None, path, "curv-type format has no physical unit metadata", "Use stored units; physical scale unverified"),
            }, path, "nibabel.freesurfer.read_morph_data")
        elif kind == "surface":
            if path.name.endswith(".gii"):
                image = nib.load(str(path))
                vertices = image.get_arrays_from_intent("NIFTI_INTENT_POINTSET")[0].data
                faces = image.get_arrays_from_intent("NIFTI_INTENT_TRIANGLE")[0].data
            else:
                vertices, faces = nib.freesurfer.read_geometry(str(path))
            span = np.ptp(vertices, axis=0).astype(float).tolist()
            details = {
                "vertex_count": field(
                    len(vertices), path, "nibabel surface pointset length"
                ),
                "face_count": field(len(faces), path, "nibabel triangle array length"),
                "face_width": field(int(faces.shape[1]) if faces.ndim == 2 else None, path, "actual geometry faces.shape"),
                "hemisphere": hemisphere(path),
                "stored_coordinate_span": field(
                    span,
                    path,
                    "coordinate max-min in stored units; not physical verification",
                ),
            }
            item["surface"] = field(details, path, "nibabel geometry reader")
        elif kind in ("annot", "label.gii", "shape.gii", "label"):
            names = []
            label_keys = []
            if kind == "annot":
                labels, _, raw_names = nib.freesurfer.read_annot(
                    str(path), orig_ids=False
                )
                names = [n.decode("utf-8", "replace") for n in raw_names]
                label_keys = list(range(len(names)))
            elif kind == "label":
                labels = nib.freesurfer.read_label(str(path))
            else:
                image = nib.load(str(path))
                labels = np.asarray(image.darrays[0].data)
                names = [entry.label for entry in image.labeltable.labels]
                label_keys = [int(entry.key) for entry in image.labeltable.labels]
            flat = np.asarray(labels).reshape(-1)
            counts = {}
            for category in ("unknown", "medialwall", "corpuscallosum"):
                indices = [
                    label_keys[i]
                    for i, name in enumerate(names)
                    if re.sub(r"[^a-z]", "", name.lower()) == category
                ]
                counts[category] = (
                    int(sum(np.count_nonzero(flat == i) for i in indices))
                    if kind in ("annot", "label.gii")
                    else None
                )
            details = {
                "label_count": field(
                    len(names) if names else None,
                    path,
                    "annotation label table",
                    None if names else "No label table",
                ),
                "vertex_count": field(
                    len(flat),
                    path,
                    "annotation/array length (sparse FreeSurfer .label is not full mesh)",
                ),
                "unassigned_vertices": field(
                    int(np.count_nonzero(flat == -1)) if kind != "shape.gii" else None,
                    path,
                    "read_annot(orig_ids=False) / label value -1",
                    (
                        "Continuous shape array has no label assignment semantics"
                        if kind == "shape.gii"
                        else None
                    ),
                ),
                "label_keys": field(label_keys, path, "annotation row indices or GIFTI label keys"),
                "label_vertex_counts": field({str(int(k)): int(np.count_nonzero(flat == k)) for k in np.unique(flat)} if kind in ("annot", "label.gii") else None, path, "actual annotation assignments; includes -1"),
                "label_names": field(
                    names, path, "decoded annotation/GIFTI label table"
                ),
                "special_vertices": field(
                    counts,
                    path,
                    "case/spacing-normalized annotation names; GIFTI keys require explicit binding",
                ),
                "surface_vertex_match": field(
                    None,
                    path,
                    "compare only explicitly supplied matching hemisphere surfaces",
                    "No surface binding yet",
                ),
            }
            item["label"] = field(details, path, "nibabel label/annotation reader")
            if kind == "shape.gii":
                item["metric"] = field({
                    "vertex_count": field(int(labels.size), path, "actual GIFTI array.size"),
                    "ndim": field(int(labels.ndim), path, "actual GIFTI array.ndim"),
                    "finite_count": field(int(np.isfinite(labels).sum()), path, "actual GIFTI finite count"),
                    "units": field(None, path, "No physical unit verification", "Unknown acquisition scale"),
                }, path, "GIFTI continuous metric array")
        elif kind in ("stats", "tsv"):
            with path.open(encoding="utf-8", errors="replace") as stream:
                rows = (
                    list(csv.DictReader(stream, delimiter="\t"))
                    if kind == "tsv"
                    else []
                )
            if kind == "tsv":
                with path.open(encoding="utf-8", errors="replace") as stream:
                    columns = next(csv.reader(stream, delimiter="\t"), [])
                item["table"] = field({
                    "columns": field(columns, path, "TSV header"),
                    "row_count": field(len(rows), path, "TSV data row count"),
                    "nonempty_columns": field({key: bool(rows) and all(row.get(key) not in (None, "") for row in rows) for key in columns}, path, "actual TSV cells; rank not inferred"),
                }, path, "csv.DictReader")
            if rows and any(
                "participant_id" in row or "subject_id" in row for row in rows
            ):
                ids = sorted(
                    {row.get("participant_id") or row.get("subject_id") for row in rows}
                    - {None, ""}
                )
                item["subject"] = field(
                    ids,
                    path,
                    "TSV explicit participant_id/subject_id deduplicated; scans are not subjects",
                )
        if path.parent.name in {"mri", "surf", "label", "stats", "scripts"}:
            scripts = path.parent.parent / "scripts"
            fastsurfer = (scripts / "recon-surf.done").is_file()
            done = scripts / ("recon-surf.done" if fastsurfer else "recon-all.done")
            log = scripts / ("recon-surf.log" if fastsurfer else "recon-all.log")
            fatal, error = [], []
            known = log.is_file()
            if known:
                with log.open(encoding="utf-8", errors="replace") as stream:
                    for number, line in enumerate(stream, 1):
                        if re.search(r"\bFATAL\b", line, re.I):
                            fatal.append(number)
                        if re.search(r"\bERROR\b", line, re.I):
                            error.append(number)
            details = {
                "done": field(done.is_file(), done, "Path.is_file"),
                "pipeline": field("FastSurfer" if fastsurfer else "FreeSurfer", done, "observed completion-marker convention"),
                "completion_marker": field(done.name, done, "actual adjacent marker filename"),
                "log_name": field(log.name, log, "pipeline-specific adjacent log"),
                "fatal_count": field(
                    len(fatal) if known else None,
                    log,
                    "case-insensitive FATAL word count by line",
                    None if known else "Log unavailable",
                ),
                "fatal_lines": field(
                    fatal if known else None, log, "1-based matching line numbers"
                ),
                "error_count": field(
                    len(error) if known else None,
                    log,
                    "case-insensitive ERROR word count by line",
                ),
                "error_lines": field(
                    error if known else None, log, "1-based matching line numbers"
                ),
            }
            item["recon"] = field(
                details,
                scripts,
                "presence and literal log counters; no severity judgment",
            )
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        item["read_error"] = field(None, path, "format reader", reason)
        target = (
            "volume"
            if kind in ("nifti", "mgz")
            else (
                "surface"
                if kind == "surface"
                else (
                    "label"
                    if kind in ("annot", "label.gii", "shape.gii", "label")
                    else None
                )
            )
        )
        if target:
            item[target] = field(None, path, "format reader", reason)
    return item


def build_profile(paths, declaration=None):
    files = [profile_file(Path(path)) for path in paths]
    for label in files:
        details = value(label["label"])
        if not details:
            continue
        lp = Path(value(label["path"]))
        candidates = [
            item
            for item in files
            if value(item["surface"])
            and Path(value(item["path"])).parent.parent == lp.parent.parent
            and value(value(item["surface"])["hemisphere"]) == value(hemisphere(lp))
            and value(hemisphere(lp)) is not None
        ]
        checks = [
            {
                "surface": value(item["path"]),
                "equal": value(value(item["surface"])["vertex_count"])
                == value(details["vertex_count"]),
            }
            for item in candidates
        ]
        details["surface_vertex_match"] = field(
            checks or None,
            lp,
            "same provided subject directory and named hemisphere; cardinality only, not registration",
            None if checks else "No matching supplied surface",
        )
    scales = []
    volumes = [item for item in files if value(item["volume"])]
    for index, left in enumerate(volumes):
        for right in volumes[index + 1 :]:
            a, b = Path(value(left["path"])), Path(value(right["path"]))
            if a.parent.parent != b.parent.parent:
                continue
            za = value(value(left["volume"])["stored_zooms"])
            zb = value(value(right["volume"])["stored_zooms"])
            scales.append(
                field(
                    {
                        "files": [str(a), str(b)],
                        "voxel_size_ratio": [
                            x / y if y else None for x, y in zip(za, zb)
                        ],
                        "interpretation": "Resolution ratios only; not proof of acquisition scale or scale misuse",
                    },
                    a,
                    "pairwise supplied same-directory volume header zooms",
                )
            )
    surfaces = [item for item in files if value(item["surface"])]
    for index, left in enumerate(surfaces):
        for right in surfaces[index + 1 :]:
            a, b = Path(value(left["path"])), Path(value(right["path"]))
            normalize = lambda text: re.sub(
                r"(?:_1mm|_native|/native/|/1mm/)", "/", text.lower()
            )
            if normalize(str(a)) != normalize(str(b)):
                continue
            sa = value(value(left["surface"])["stored_coordinate_span"])
            sb = value(value(right["surface"])["stored_coordinate_span"])
            scales.append(
                field(
                    {
                        "files": [str(a), str(b)],
                        "vertex_coordinate_span_ratio": [
                            x / y if y else None for x, y in zip(sa, sb)
                        ],
                        "interpretation": "Stored-coordinate extent ratios for conventionally named candidate copies; identity/physical scale not verified",
                    },
                    a,
                    "provided surface bounds and explicit native/_1mm filename normalization",
                )
            )
    # Bind actual annotation support to the supplied cortex index subset.
    for item in files:
        if value(item["format"]) != "annot" or item.get("read_error"):
            continue
        path = Path(value(item["path"]))
        cortex = path.with_name(path.name[:2] + ".cortex.label")
        if not any(value(f["path"]) == str(cortex) for f in files):
            continue
        import nibabel as nib
        import numpy as np
        labels = nib.freesurfer.read_annot(str(path), orig_ids=False)[0]
        indices = nib.freesurfer.read_label(str(cortex)).astype(int)
        if np.any(indices < 0) or np.any(indices >= len(labels)) or len(np.unique(indices)) != len(indices):
            item["read_error"] = field(None, cortex, "cortex index validation", "Duplicate or out-of-range cortex vertex IDs")
            continue
        retained = labels[indices]
        value(item["label"])["cortex_retained_label_counts"] = field(
            {str(int(k)): int(np.count_nonzero(retained == k)) for k in np.unique(retained)},
            [str(path), str(cortex)], "read_annot(orig_ids=False) intersect explicit cortex indices; no morphometry aggregation")
    return {
        "schema_version": "primatex.data_profile.v1",
        "files": files,
        "species": {
            "declared": field(
                declaration,
                "user_request",
                "explicit species declaration from authenticated task; no filename inference",
                None if declaration else "No explicit declaration",
            ),
            "verified": field(
                None,
                "trusted_metadata_registry",
                "host-owned trusted metadata only",
                "No trusted metadata binding configured",
            ),
        },
        "physical_scale_verified": field(
            None,
            "trusted_metadata_registry",
            "acquisition provenance verification",
            "Header units alone do not verify physical scale",
        ),
        "scale_notes": scales,
    }


def main(request):
    """Arguments are embedded by the host in the frozen program, never /work JSON."""
    profile = build_profile(request["paths"], request.get("declared_species"))
    profile["request_id"] = request["request_id"]
    Path("/work/data_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    print("Data profile generated; no image analysis performed")
