"""Round 15: independent host reference for global morphometry and cross-species ratios."""
import gzip
import importlib
import importlib.util
from pathlib import Path
import struct
import sys
import types

_BACKEND = Path(__file__).resolve().parents[1] / "backend"


def _load():
    try:
        from test_analysis_agent import agent
        return importlib.import_module(agent.__package__ + ".analysis_global_reference")
    except Exception:
        pkg = types.ModuleType("_r15_backend")
        pkg.__path__ = [str(_BACKEND)]
        sys.modules["_r15_backend"] = pkg
        for name in ("analysis_numeric_reference", "analysis_global_reference"):
            spec = importlib.util.spec_from_file_location(f"_r15_backend.{name}", _BACKEND / f"{name}.py")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
        return sys.modules["_r15_backend.analysis_global_reference"]


g = _load()

ASEG = """# Title Segmentation Statistics
# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 1200000.000000, mm^3
# Measure EstimatedTotalIntraCranialVol, eTIV, Estimated Total Intracranial Volume, 1500000.000000, mm^3
"""


def hemi(area, thick):
    return (f"# Measure Cortex, WhiteSurfArea, White Surface Total Area, {area}, mm^2\n"
            f"# Measure Cortex, MeanThickness, Mean Thickness, {thick}, mm\n")


def write(tmp, name, text):
    path = Path(tmp) / name
    path.write_text(text)
    return path


def mgz(tmp, dims=(4, 4, 4), spacing=(0.5, 0.5, 0.5), nonzero=10):
    w, h, d = dims
    header = struct.pack(">7i", 1, w, h, d, 1, 0, 0) + struct.pack(">h", 1) + struct.pack(">3f", *spacing)
    header += b"\0" * (284 - len(header))
    data = bytes([1] * nonzero + [0] * (w * h * d - nonzero))
    path = Path(tmp) / "brainmask.mgz"
    with gzip.open(path, "wb") as stream:
        stream.write(header + data)
    return path


def test_parse_and_globals_not_rescaled(tmp_path):
    out = g.subject_globals(aseg_stats=write(tmp_path, "aseg.stats", ASEG),
                            hemi_stats={"lh": write(tmp_path, "lh.s", hemi(90000, 2.5)),
                                        "rh": write(tmp_path, "rh.s", hemi(86000, 2.7))},
                            rescaled=False)
    s = out["stored"]
    assert s["brain_volume_mm3"] == 1200000.0 and s["etiv_mm3"] == 1500000.0
    assert s["total_area_mm2"] == 176000.0
    assert abs(s["mean_thickness_mm"] - (90000 * 2.5 + 86000 * 2.7) / 176000) < 1e-12
    assert out["physical"] == s and out["scale_status"] == "verified_not_rescaled"


def test_rescaled_conversion_and_unknown_scale(tmp_path):
    hs = {"lh": write(tmp_path, "lh.s", hemi(40000, 4.2)), "rh": write(tmp_path, "rh.s", hemi(40800, 4.2))}
    out = g.subject_globals(hemi_stats=hs, mask_volume=mgz(tmp_path), rescaled=True, scale_k=2.0)
    assert out["stored"]["brain_volume_mm3"] == 10 * 0.125
    assert abs(out["physical"]["mean_thickness_mm"] - 2.1) < 1e-12
    assert out["physical"]["total_area_mm2"] == 80800 / 4
    assert out["physical"]["brain_volume_mm3"] == 1.25 / 8
    unknown = g.subject_globals(hemi_stats=hs)
    assert unknown["scale_status"] == "unknown" and all(v is None for v in unknown["physical"].values())
    try:
        g.subject_globals(hemi_stats=hs, rescaled=True)
    except ValueError as exc:
        assert "scale factor" in str(exc)
    else:
        raise AssertionError("rescaled without k must fail")


def test_missing_measures_rejected(tmp_path):
    try:
        g.subject_globals(hemi_stats={"lh": write(tmp_path, "lh.s", "# Measure Cortex, NumVert, n, 5, unitless\n"),
                                      "rh": write(tmp_path, "rh.s", hemi(1, 1))})
    except ValueError as exc:
        assert "WhiteSurfArea" in str(exc)
    else:
        raise AssertionError("missing measures must fail")


def test_cross_species_ratio():
    rows = [{"subject": "h1", "species": "human", "physical": {"total_area_mm2": 180000.0, "mean_thickness_mm": 2.6}},
            {"subject": "h2", "species": "human", "physical": {"total_area_mm2": 172000.0, "mean_thickness_mm": 2.5}},
            {"subject": "m1", "species": "macaque", "physical": {"total_area_mm2": 20000.0, "mean_thickness_mm": 2.1}},
            {"subject": "m2", "species": "macaque", "physical": {m: None for m in g.METRICS}}]
    out = g.cross_species_summary(rows)
    area = next(r for r in out["summary"] if r["metric"] == "total_area_mm2")
    assert area["human_n"] == 2 and area["macaque_n"] == 1 and area["ratio"] == 176000.0 / 20000.0
    assert out["excluded_unknown_scale"] == ["m2"] and out["homology_required"] is False


def test_hull_ratio_with_scipy(tmp_path):
    try:
        import scipy  # noqa: F401
    except ImportError:
        return
    def surface(path, verts, faces):
        raw = b"\xff\xff\xfe" + b"synthetic\n\n" + struct.pack(">ii", len(verts), len(faces))
        raw += b"".join(struct.pack(">3f", *v) for v in verts)
        raw += b"".join(struct.pack(">3i", *f) for f in faces)
        path.write_bytes(raw)
        return path
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
    faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    pial = {h: surface(tmp_path / f"{h}.pial", verts, faces) for h in ("lh", "rh")}
    out = g.subject_globals(pial=pial, rescaled=False)
    assert abs(out["stored"]["hull_ratio"] - 1.0) < 1e-9


if __name__ == "__main__":
    import tempfile
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as tmp:
                fn(Path(tmp)) if fn.__code__.co_argcount else fn()
            print("ok", name)
