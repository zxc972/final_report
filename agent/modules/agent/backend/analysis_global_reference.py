"""Independent host reference for global morphometry and cross-species ratios.

Standard library only (the hull ratio reuses analysis_numeric_reference.hull_measure,
which itself uses SciPy/Qhull for the hull primitive). Never imported into Agent
images and never imports primatex_ops.

Per subject (single subject, host-verifiable):
  brain_volume_mm3   aseg.stats BrainSegVol; else voxel count of a mask volume
                     (mri/brainmask.mgz > 0) times voxel volume
  etiv_mm3           aseg.stats eTIV when present (None otherwise)
  total_area_mm2     lh + rh WhiteSurfArea from the cortical parcellation stats
  mean_thickness_mm  area-weighted mean of lh/rh MeanThickness
  hull_ratio         (lh + rh pial area) / (lh + rh convex-hull area) when pial
                     surfaces are supplied; dimensionless
Scale: values are stored values divided by k**power (length 1, area 2, volume 3)
when the subject was rescaled by a verified factor k; unknown scale is reported,
never assumed.

Cross-species summary: per-species means and the ratio of species means for
each metric. Whole-brain measures need no regional homology.

Sources: FreeSurfer stats file format ("# Measure" lines:
https://surfer.nmr.mgh.harvard.edu/fswiki/MorphometryStats); MGH format
(https://surfer.nmr.mgh.harvard.edu/fswiki/FsTutorial/MghFormat).
"""
from __future__ import annotations

import gzip
import math
from pathlib import Path
import struct
from typing import Mapping, Sequence

POWERS = {"mean_thickness_mm": 1, "total_area_mm2": 2, "brain_volume_mm3": 3,
          "etiv_mm3": 3, "hull_ratio": 0}
METRICS = tuple(POWERS)
MGH_TYPES = {0: ("B", 1), 1: (">i", 4), 3: (">f", 4), 4: (">h", 2)}
MAX_VOXELS = 512 * 512 * 512


def parse_measures(path) -> dict:
    """Return {short_name: (value, unit)} from '# Measure' lines of a stats file."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("# Measure "):
            continue
        parts = [p.strip() for p in line[len("# Measure "):].split(",")]
        if len(parts) < 5:
            continue
        try:
            value = float(parts[-2])
        except ValueError:
            continue
        if not math.isfinite(value):
            raise ValueError(f"Nonfinite measure in {path}")
        out[parts[1]] = (value, parts[-1])
    return out


def mask_volume_mm3(path) -> float:
    """Voxel count (> 0) times voxel volume for an .mgz/.mgh volume."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".mgz" else open
    with opener(path, "rb") as stream:
        header = stream.read(284)
        if len(header) < 284:
            raise ValueError("Truncated MGH header")
        version, w, h, d, frames, kind = struct.unpack(">6i", header[:24])
        if version != 1 or kind not in MGH_TYPES or frames != 1 or min(w, h, d) <= 0:
            raise ValueError("Unsupported MGH volume")
        good_ras = struct.unpack(">h", header[28:30])[0]
        spacing = struct.unpack(">3f", header[30:42]) if good_ras else (1.0, 1.0, 1.0)
        if any(not math.isfinite(v) or v <= 0 for v in spacing):
            raise ValueError("Invalid MGH voxel spacing")
        count = w * h * d
        if not 0 < count <= MAX_VOXELS:
            raise ValueError("Out-of-range MGH dimensions")
        fmt, size = MGH_TYPES[kind]
        raw = stream.read(count * size)
        if len(raw) != count * size:
            raise ValueError("Truncated MGH data")
    if fmt == "B":
        nonzero = count - raw.count(0)
    else:
        nonzero = 0
        for (number,) in struct.iter_unpack(fmt, raw):
            if not math.isfinite(number):
                raise ValueError("Nonfinite MGH support value")
            nonzero += number > 0
    return nonzero * abs(spacing[0] * spacing[1] * spacing[2])


def subject_globals(aseg_stats=None, hemi_stats: Mapping[str, str] | None = None,
                    mask_volume=None, pial: Mapping[str, str] | None = None,
                    scale_k: float | None = None, rescaled: bool | None = None) -> dict:
    """Compute one subject's global metrics in stored and scale-corrected units."""
    stored = {m: None for m in METRICS}
    sources = {}
    if aseg_stats:
        measures = parse_measures(aseg_stats)
        if "BrainSegVol" in measures:
            stored["brain_volume_mm3"] = measures["BrainSegVol"][0]
            sources["brain_volume_mm3"] = "aseg.stats BrainSegVol"
        if "eTIV" in measures:
            stored["etiv_mm3"] = measures["eTIV"][0]
            sources["etiv_mm3"] = "aseg.stats eTIV"
    if stored["brain_volume_mm3"] is None and mask_volume:
        stored["brain_volume_mm3"] = mask_volume_mm3(mask_volume)
        sources["brain_volume_mm3"] = "mask voxel count x voxel volume"
    if hemi_stats:
        if set(hemi_stats) != {"lh", "rh"}:
            raise ValueError("Both hemisphere stats files are required")
        areas, thick = {}, {}
        for hemi, path in hemi_stats.items():
            measures = parse_measures(path)
            if "WhiteSurfArea" not in measures or "MeanThickness" not in measures:
                raise ValueError(f"{hemi} stats lack WhiteSurfArea or MeanThickness")
            areas[hemi] = measures["WhiteSurfArea"][0]
            thick[hemi] = measures["MeanThickness"][0]
        total = areas["lh"] + areas["rh"]
        if total <= 0:
            raise ValueError("Nonpositive total white surface area")
        stored["total_area_mm2"] = total
        stored["mean_thickness_mm"] = (areas["lh"] * thick["lh"] + areas["rh"] * thick["rh"]) / total
        sources["total_area_mm2"] = "lh+rh WhiteSurfArea"
        sources["mean_thickness_mm"] = "area-weighted lh/rh MeanThickness"
    if pial:
        from .analysis_numeric_reference import hull_measure
        surf = hull = 0.0
        for hemi in ("lh", "rh"):
            measured = hull_measure(pial[hemi])
            surf += measured["surface_area"]
            hull += measured["hull_area"]
        stored["hull_ratio"] = surf / hull
        sources["hull_ratio"] = "sum pial area / sum convex-hull area"
    if rescaled is True:
        if not (scale_k and scale_k > 0):
            raise ValueError("A verified positive scale factor is required when rescaled")
        k, scale_status = float(scale_k), "verified"
    elif rescaled is False:
        k, scale_status = 1.0, "verified_not_rescaled"
    else:
        k, scale_status = None, "unknown"
    physical = {}
    for metric, value in stored.items():
        if value is None or k is None:
            physical[metric] = None
        else:
            physical[metric] = value / (k ** POWERS[metric])
    return {"stored": stored, "physical": physical, "scale_k": k,
            "scale_status": scale_status, "sources": sources}


def cross_species_summary(rows: Sequence[Mapping[str, object]],
                          numerator: str = "human", denominator: str = "macaque") -> dict:
    """rows: [{"subject", "species", "physical": {metric: value}}]. Ratio of species means."""
    by_species: dict[str, dict[str, list[float]]] = {}
    unknown_scale = []
    for row in rows:
        species = str(row["species"])
        values = row.get("physical") or {}
        if all(values.get(m) is None for m in METRICS):
            unknown_scale.append(str(row["subject"]))
        for metric in METRICS:
            value = values.get(metric)
            if value is not None:
                by_species.setdefault(species, {}).setdefault(metric, []).append(float(value))
    summary = []
    for metric in METRICS:
        num = by_species.get(numerator, {}).get(metric, [])
        den = by_species.get(denominator, {}).get(metric, [])
        if not num or not den:
            continue
        mean_num, mean_den = math.fsum(num) / len(num), math.fsum(den) / len(den)
        summary.append({"metric": metric, f"{numerator}_n": len(num), f"{numerator}_mean": mean_num,
                        f"{denominator}_n": len(den), f"{denominator}_mean": mean_den,
                        "ratio": mean_num / mean_den if mean_den else None})
    return {"summary": summary, "excluded_unknown_scale": unknown_scale,
            "measure_kind": "ratio", "homology_required": False}
