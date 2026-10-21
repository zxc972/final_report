"""Read-only structural image operations 1.0.0, implemented with NiBabel/NumPy.

No implicit physical rescaling, atlas mapping or species/homology inference.
Callers choose files, exclusions, masks and outputs. No task reference answers.
"""

from __future__ import annotations
from pathlib import Path
import shlex
import nibabel as nib
import numpy as np

__version__ = "1.0.0"


def _vector(data, name):
    data = np.asarray(data)
    if data.ndim != 1:
        raise ValueError(name + " must be a one-dimensional vertex vector")
    return data


def _mesh(vertices, faces):
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError("vertices must be a finite (N, 3) array")
    if (
        faces.ndim != 2
        or faces.shape[1] != 3
        or not np.issubdtype(faces.dtype, np.integer)
    ):
        raise ValueError("faces must be an integer (M, 3) array")
    if (
        not len(vertices)
        or not len(faces)
        or faces.min() < 0
        or faces.max() >= len(vertices)
    ):
        raise ValueError("Mesh must be nonempty with valid vertex indices")
    return vertices, faces.astype(np.int64, copy=False)


def read_surface(path):
    """FS triangle/GIFTI surface -> (vertices, faces); retain stored coordinates.

    Stored units and space are not independently verified physical mm.
    """
    if str(path).endswith(".gii"):
        image = nib.load(str(path))
        points = image.get_arrays_from_intent("NIFTI_INTENT_POINTSET")
        triangles = image.get_arrays_from_intent("NIFTI_INTENT_TRIANGLE")
        if len(points) != 1 or len(triangles) != 1:
            raise ValueError("GIFTI requires one pointset and one triangle array")
        return _mesh(points[0].data, triangles[0].data)
    return _mesh(*nib.freesurfer.read_geometry(str(path)))


def read_surface_metric(path):
    """FS thickness/curv/sulc/area or one GIFTI SHAPE -> float64 vertex vector.

    No conversion; units remain unknown unless independently established.
    Multi-map GIFTI is rejected: map selection must be explicit.
    """
    if str(path).endswith(".gii"):
        arrays = nib.load(str(path)).get_arrays_from_intent("NIFTI_INTENT_SHAPE")
        if len(arrays) != 1:
            raise ValueError("Expected exactly one GIFTI SHAPE array")
        data = arrays[0].data
    else:
        data = nib.freesurfer.read_morph_data(str(path))
    return _vector(data, "metric").astype(np.float64)


def read_annotation(path):
    """FS .annot -> (vertex_labels, names, colortable); labels are positional IDs.

    orig_ids=False: unassigned=-1; names decoded UTF-8. Table is RGBT+packed ID,
    not RGBA. Dimensionless keys/names do not establish homology or species.
    """
    labels, table, names = nib.freesurfer.read_annot(str(path), orig_ids=False)
    return labels.astype(np.int64), [n.decode("utf-8") for n in names], table


def read_label(path):
    """FS ASCII .label -> unique nonnegative vertex indices (not a boolean mask).

    Dimensionless IDs; only apply to the corresponding mesh.
    """
    ids = nib.freesurfer.read_label(str(path)).astype(np.int64)
    if len(np.unique(ids)) != len(ids) or (ids < 0).any():
        raise ValueError("Label indices must be unique and nonnegative")
    return ids


def read_label_gifti(path):
    """One GIFTI LABEL -> (integer keys, key-to-name dict), original GIFTI IDs.

    Dimensionless; IDs are not remapped to FS positional color-table indices.
    """
    image = nib.load(str(path))
    arrays = image.get_arrays_from_intent("NIFTI_INTENT_LABEL")
    if len(arrays) != 1 or not np.issubdtype(arrays[0].data.dtype, np.integer):
        raise ValueError("Expected exactly one integer GIFTI LABEL array")
    return (
        _vector(arrays[0].data, "labels").astype(np.int64),
        image.labeltable.get_labels_as_dict(),
    )


def vertex_area(vertices, faces):
    """Barycentric area/vertex: one third of each incident triangle area.

    Squared stored-coordinate units; sum equals full mesh area. This differs
    from mixed Voronoi area and some FreeSurfer area products.
    """
    vertices, faces = _mesh(vertices, faces)
    tri = vertices[faces]
    areas = (
        np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        / 2
    )
    result = np.zeros(len(vertices), dtype=np.float64)
    np.add.at(result, faces.ravel(), np.repeat(areas / 3, 3))
    return result


def _mask(mask, count):
    if mask is None:
        return np.ones(count, dtype=bool)
    values = _vector(mask, "mask")
    if values.dtype == bool:
        if len(values) != count:
            raise ValueError("Boolean mask length must equal metric length")
        return values.copy()
    if not np.issubdtype(values.dtype, np.integer):
        raise ValueError("mask must be boolean or integer vertex indices")
    if len(values) and (values.min() < 0 or values.max() >= count):
        raise ValueError("Mask index outside metric")
    if len(np.unique(values)) != len(values):
        raise ValueError("Mask indices must be unique")
    result = np.zeros(count, dtype=bool)
    result[values] = True
    return result


def parcel_summary(metric, vertex_labels, label_set, mask=None, weights=None):
    """Explicit label/mask summary; list of {key:int,name:str}, keys or key:name.

    Rows: label_key, name, vertex_count, mean, std_population, median,
    zero_count, weight_sum. Moments retain metric units. Weights must be finite,
    nonnegative and match vertices. Weighted population variance; weighted median
    is the first ordered value reaching half total weight. Unweighted median is
    numpy.median (even-N midpoint). Counts are unweighted. Empty/zero-weight
    groups have null moments. No implicit exclusions: caller omits -1/unknown
    and supplies corresponding cortex indices. Nonfinite selected values fail.
    """
    metric = _vector(metric, "metric").astype(np.float64)
    labels = _vector(vertex_labels, "vertex_labels")
    if len(metric) != len(labels) or not np.issubdtype(labels.dtype, np.integer):
        raise ValueError("Integer labels and metric must have equal vertex counts")
    selected = _mask(mask, len(metric))
    if not np.isfinite(metric[selected]).all():
        raise ValueError("Selected metric contains non-finite values")
    weight = None
    if weights is not None:
        weight = _vector(weights, "weights").astype(np.float64)
        if (
            len(weight) != len(metric)
            or not np.isfinite(weight).all()
            or (weight < 0).any()
        ):
            raise ValueError("Weights must be finite, nonnegative and match metric")
    if isinstance(label_set, dict):
        entries = [{"key": int(k), "name": str(n)} for k, n in label_set.items()]
    else:
        entries = [
            item if isinstance(item, dict) else {"key": item, "name": str(item)}
            for item in label_set
        ]
    keys = [item["key"] for item in entries]
    if any(
        not isinstance(k, (int, np.integer)) or isinstance(k, bool) for k in keys
    ) or len(set(keys)) != len(keys):
        raise ValueError("label_set requires unique integer keys")
    rows = []
    for item in entries:
        included = selected & (labels == item["key"])
        values = metric[included]
        w = weight[included] if weight is not None else None
        total = (
            float(np.sum(w, dtype=np.float64)) if w is not None else float(len(values))
        )
        mean = std = median = None
        if len(values) and total > 0:
            mean = float(np.average(values, weights=w))
            std = float(np.sqrt(np.average((values - mean) ** 2, weights=w)))
            if w is None:
                median = float(np.median(values))
            else:
                order = np.argsort(values, kind="stable")
                median = float(
                    values[order[np.searchsorted(np.cumsum(w[order]), total / 2)]]
                )
        rows.append(
            {
                "label_key": int(item["key"]),
                "name": str(item["name"]),
                "vertex_count": int(len(values)),
                "mean": mean,
                "std_population": std,
                "median": median,
                "zero_count": int(np.count_nonzero(values == 0)),
                "weight_sum": total,
            }
        )
    return rows


def read_stats_table(path):
    """FS text stats -> actual declared columns, string rows, measures, source.

    Dynamically binds ColHeaders/TableCol; units follow original headers with
    no conversion. ThickAvg is not equated with another thickness statistic.
    """
    headers, declared, rows, measures = None, {}, [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("# ColHeaders "):
            headers = line.split()[2:]
        elif line.startswith("# TableCol "):
            parts = shlex.split(line)
            if len(parts) >= 5 and parts[3] == "ColHeader":
                declared[int(parts[2])] = parts[4]
        elif line.startswith("# Measure "):
            measures.append(line[len("# Measure ") :])
        elif line.strip() and not line.startswith("#"):
            columns = headers or [declared[k] for k in sorted(declared)]
            values = line.split()
            if (
                not columns
                or len(columns) != len(values)
                or len(set(columns)) != len(columns)
            ):
                raise ValueError("Stats data and declared columns do not match")
            rows.append(dict(zip(columns, values)))
    return {
        "columns": headers or [declared[k] for k in sorted(declared)],
        "rows": rows,
        "measures": measures,
        "source": str(path),
        "units": "Per source headers; no conversion",
    }


def convex_hull_area_ratio(vertices, faces):
    """Full triangle area / same-vertices 3D convex hull area; dict of values.

    SciPy/Qhull denominator without jitter/decimation; areas in squared stored
    units, ratio dimensionless. Whole-surface descriptive ratio is NOT lGI.
    """
    from scipy.spatial import ConvexHull

    vertices, faces = _mesh(vertices, faces)
    tri = vertices[faces]
    area = float(
        np.sum(
            np.linalg.norm(
                np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1
            )
            / 2,
            dtype=np.float64,
        )
    )
    hull_area = float(ConvexHull(vertices).area)
    if not np.isfinite(area) or not np.isfinite(hull_area) or hull_area <= 0:
        raise ValueError("Areas must be finite with a positive hull denominator")
    return {
        "surface_area": area,
        "hull_area": hull_area,
        "area_ratio": area / hull_area,
        "area_units": "squared stored-coordinate units; physical scale unverified",
        "ratio_units": "dimensionless",
        "is_local_gyrification_index": False,
    }


def nifti_info(path):
    """NIfTI/MGH header -> shape, stored voxel sizes, full affine, declared units.

    No voxel load. Header-declared mm is not verified acquisition calibration;
    unknown units stay unknown and are not implicitly converted to mm.
    """
    image = nib.load(str(path))
    units = (
        image.header.get_xyzt_units()[0]
        if hasattr(image.header, "get_xyzt_units")
        else "unknown"
    )
    return {
        "shape": [int(n) for n in image.shape],
        "voxel_size": [float(n) for n in image.header.get_zooms()[:3]],
        "voxel_size_units": units,
        "affine": image.affine.tolist(),
        "physical_scale_verified": False,
    }
