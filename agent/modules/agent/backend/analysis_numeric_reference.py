"""Independent host readers and calculations; never imported into Agent images.

Format locations: NiBabel freesurfer IO and FreeSurfer annotation documentation.
Only the hull primitive shares SciPy/Qhull; binary IO, triangle accumulation and
ROI summaries are independent stdlib implementations. No primatex_ops import.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import statistics
import struct

MAX_VERTICES = 10000000


def take(stream, size):
    raw = stream.read(size)
    if len(raw) != size:
        raise ValueError("Truncated FreeSurfer input")
    return raw


def integer(stream):
    return struct.unpack(">i", take(stream, 4))[0]


def count(stream, maximum=MAX_VERTICES):
    number = integer(stream)
    if not 0 <= number <= maximum:
        raise ValueError("Out-of-range binary count")
    return number


def string(stream):
    size = count(stream, 1048576)
    return take(stream, size).rstrip(b"\0").decode("utf-8")


def read_metric(path):
    with Path(path).open("rb") as stream:
        magic = int.from_bytes(take(stream, 3), "big")
        if magic == 16777215:
            vertices = count(stream)
            count(stream, 100000000)
            if integer(stream) != 1:
                raise ValueError("Expected one metric per vertex")
            values = [x[0] for x in struct.iter_unpack(">f", take(stream, 4 * vertices))]
        else:
            vertices = magic
            take(stream, 3)
            if vertices > MAX_VERTICES:
                raise ValueError("Too many old-format vertices")
            values = [x[0] / 100 for x in struct.iter_unpack(">h", take(stream, 2 * vertices))]
    if not values or not all(math.isfinite(x) for x in values):
        raise ValueError("Empty or nonfinite metric")
    return values


def read_annotation(path):
    with Path(path).open("rb") as stream:
        vertices = count(stream)
        pairs = list(struct.iter_unpack(">ii", take(stream, vertices * 8)))
        if sorted(index for index, _ in pairs) != list(range(vertices)):
            raise ValueError("Annotation vertex identities are incomplete")
        if integer(stream) == 0:
            raise ValueError("Annotation lacks a color table")
        entries = integer(stream)
        table = {}
        if entries > 0:
            string(stream)
            indices = range(entries)
            sparse = False
        elif entries == -2:
            count(stream)
            string(stream)
            indices = range(count(stream))
            sparse = True
        else:
            raise ValueError("Unsupported annotation version")
        for position in indices:
            index = count(stream) if sparse else position
            name = string(stream)
            red, green, blue, transparency = struct.unpack(">iiii", take(stream, 16))
            if not all(0 <= c <= 255 for c in [red, green, blue, transparency]):
                raise ValueError("Invalid annotation color")
            table[index] = (name, red + (green << 8) + (blue << 16))
    packed = {color: index for index, (_, color) in table.items() if color != 0}
    labels = [-1] * vertices
    for index, color in pairs:
        if color != 0 and color not in packed:
            raise ValueError("Assignment absent from annotation color table")
        labels[index] = packed.get(color, -1)
    return labels, {index: item[0] for index, item in table.items()}


def read_cortex(path, vertices):
    with Path(path).open() as stream:
        if not stream.readline().startswith("#"):
            raise ValueError("Invalid ASCII label header")
        expected = int(stream.readline())
        rows = [line.split() for line in stream if line.strip()]
    ids = [int(row[0]) for row in rows]
    if len(ids) != expected or len(set(ids)) != len(ids):
        raise ValueError("Invalid cortex label count or duplicate vertex")
    if any(index < 0 or index >= vertices for index in ids):
        raise ValueError("Out-of-range cortex vertex")
    return set(ids)


def summarize(values):
    n = len(values)
    if not n:
        raise ValueError("Requested parcel is empty")
    mean = math.fsum(values) / n
    return {
        "vertex_count": n,
        "mean": mean,
        "std_population": math.sqrt(math.fsum((x - mean) ** 2 for x in values) / n),
        "median": statistics.median(values),
        "zero_count": sum(x == 0 for x in values),
    }


def roi_rows(plan, bundle, resolve):
    result = []
    for scope, group in bundle["label_sets"].items():
        subject, hemisphere = scope.rsplit("/", 1)
        labels, names = read_annotation(resolve(group["annotation"]))
        cortex = read_cortex(resolve(group["cortex_label"]), len(labels))
        metrics = [
            row["inputs"]["metric_path"] for row in bundle["operations"]["calls"]
            if row["function"] == "parcel_summary" and row["scope"] == scope
        ]
        if not metrics:
            raise ValueError("No registered metric binding")
        for metric_path in metrics:
            if metric_path not in plan["data"]["files"]:
                raise ValueError("Unsealed metric input")
            values = read_metric(resolve(metric_path))
            if len(values) != len(labels):
                raise ValueError("Metric/annotation mesh mismatch")
            for selected in group["labels"]:
                key, name = selected["key"], selected["name"]
                if key < 0 or names.get(key) != name:
                    raise ValueError("Sealed label identity disagrees with source")
                data = [values[index] for index in sorted(cortex) if labels[index] == key]
                result.append({
                    "subject": subject, "hemisphere": hemisphere,
                    "metric": metric_path.rsplit(".", 1)[-1],
                    "label_key": key, "name": name, **summarize(data),
                })
    if not result:
        raise ValueError("ROI reference has no rows")
    return result


def read_surface(path):
    with Path(path).open("rb") as stream:
        if take(stream, 3) != b"\xff\xff\xfe":
            raise ValueError("Expected triangular FreeSurfer surface")
        stream.readline(1048576)
        stream.readline(1048576)
        nvertices, nfaces = count(stream), count(stream, 20000000)
        vertices = list(struct.iter_unpack(">fff", take(stream, 12 * nvertices)))
        faces = list(struct.iter_unpack(">iii", take(stream, 12 * nfaces)))
    if any(not math.isfinite(c) for vertex in vertices for c in vertex):
        raise ValueError("Nonfinite mesh coordinate")
    if any(i < 0 or i >= nvertices for face in faces for i in face):
        raise ValueError("Out-of-range mesh face")
    return vertices, faces


def triangle_area(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    return math.sqrt(math.fsum(x*x for x in cross)) / 2


def hull_measure(path):
    from scipy.spatial import ConvexHull
    vertices, faces = read_surface(path)
    surface_area = math.fsum(triangle_area(*(vertices[i] for i in face)) for face in faces)
    hull = ConvexHull(vertices)
    hull_area = float(hull.area)
    if not 0 < hull_area < math.inf or not 0 < surface_area < math.inf:
        raise ValueError("Degenerate surface or hull")
    return {"surface_area": surface_area, "hull_area": hull_area, "area_ratio": surface_area/hull_area}


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != "--hull":
        raise SystemExit("Registered host hull worker only")
    print(json.dumps(hull_measure(sys.argv[2]), allow_nan=False))
