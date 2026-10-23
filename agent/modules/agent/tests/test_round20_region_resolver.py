"""Round 20: geometric region resolution (algorithm 2)."""
import importlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
KNOWLEDGE = ROOT / "knowledge_analysis"


def _load():
    try:
        from test_analysis_agent import agent
        return importlib.import_module(agent.__package__ + ".analysis_region_resolver")
    except Exception:
        name = "_r20_region_resolver"
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, BACKEND / "analysis_region_resolver.py")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
        return sys.modules[name]


rr = _load()


def _strip():
    regions = ["frontal"] * 50 + ["temporal"] * 50
    labels = ["A"] * 30 + ["B"] * 30 + ["C"] * 40
    return regions, labels


def test_inclusion_assignment_and_diagnostics():
    regions, labels = _strip()
    out = rr.resolve(regions, labels)
    f = out["regions"]["frontal"]
    assert f["labels"] == ["A", "B"]
    assert math.isclose(out["inclusion"]["B"]["frontal"], 20 / 30)
    assert math.isclose(f["coverage"], 1.0) and math.isclose(f["purity"], 50 / 60)
    assert math.isclose(f["dice"], 100 / 110)
    t = out["regions"]["temporal"]
    assert t["labels"] == ["C"] and math.isclose(t["coverage"], 40 / 50)
    assert f["verdict"] == "resolved" and t["verdict"] == "resolved"


def test_ambiguous_label_is_unassigned_and_qualifies():
    regions = ["frontal"] * 50 + ["parietal"] * 50
    labels = ["A"] * 40 + ["D"] * 20 + ["E"] * 40   # D split 10/10
    out = rr.resolve(regions, labels, theta=0.6)
    assert out["assignment"]["D"] is None and out["unassigned"] == ["D"]
    assert out["regions"]["frontal"]["ambiguous"] == ["D"]
    assert out["regions"]["frontal"]["verdict"] == "qualified"
    strict = rr.resolve(regions, labels, theta=1.0)
    assert strict["assignment"]["A"] == "frontal"


def test_excluded_and_unassigned_vertices_do_not_count():
    names = {0: "unknown", 1: "superiorfrontal", 2: "corpuscallosum"}
    assert rr.named([0, 1, 2, -1], names) == [None, "superiorfrontal", None, None]
    out = rr.resolve(["frontal", "frontal", None], ["X", None, "X"])
    assert math.isclose(out["inclusion"]["X"]["frontal"], 0.5)
    assert math.isclose(out["regions"]["frontal"]["coverage"], 0.5)


def test_area_weights_change_the_decision():
    regions = ["frontal", "frontal", "temporal", "temporal"]
    labels = ["B", "B", "B", "C"]
    assert rr.resolve(regions, labels)["assignment"]["B"] == "frontal"
    weighted = rr.resolve(regions, labels, weights=[1, 1, 5, 1])
    assert weighted["assignment"]["B"] == "temporal"
    square = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    areas = rr.vertex_areas(square, [(0, 1, 2), (0, 2, 3)])
    assert math.isclose(sum(areas), 1.0)
    assert math.isclose(areas[0], 1 / 3) and math.isclose(areas[1], 1 / 6)


def test_identical_parcellations_are_recovered_exactly():
    rng = random.Random(7)
    lobes = ["frontal", "temporal", "parietal", "occipital"]
    label_of = {f"L{i}": lobes[i % 4] for i in range(20)}
    labels = [f"L{rng.randrange(20)}" for _ in range(2000)]
    regions = [label_of[l] for l in labels]
    out = rr.resolve(regions, labels, weights=[rng.uniform(0.5, 1.5) for _ in labels])
    assert out["assignment"] == label_of
    assert all(math.isclose(r["dice"], 1.0) for r in out["regions"].values())
    assert rr.evaluate(out["assignment"], label_of)["accuracy"] == 1.0


def test_sourced_mapping_and_name_baselines():
    doc = json.loads((KNOWLEDGE / "lobar_mapping.json").read_text(encoding="utf-8"))
    ref = rr.regions_from_mapping(["superiorfrontal", "lingual", None, "insula"], doc["records"], "DK")
    assert ref == ["frontal", "occipital", None, "insula"]
    dkt = rr.name_baseline(["superiorfrontal", "G_front_sup", "unknown"], doc["records"], "DKT")
    assert dkt == {"superiorfrontal": "frontal", "G_front_sup": None}
    kw = rr.keyword_baseline(["G_front_sup", "S_central", "G_cingul-Post-dorsal", "G_temporal_middle"])
    assert kw == {"G_front_sup": "frontal", "S_central": None,
                  "G_cingul-Post-dorsal": "cingulate", "G_temporal_middle": "temporal"}


def test_evaluate_sweep_geometric_score_and_agreement():
    regions, labels = _strip()
    ref = {"A": "frontal", "B": "frontal", "C": "temporal"}
    score = rr.evaluate({"A": "frontal", "B": None, "C": "temporal"}, ref)
    assert math.isclose(score["accuracy"], 2 / 3) and score["precision_assigned"] == 1.0
    rows = rr.theta_sweep(regions, labels, reference=ref, thetas=(0.5, 0.7))
    assert rows[0]["accuracy"] == 1.0 and rows[1]["unassigned"] == 1
    geo = rr.geometric_score({"A": "frontal", "C": "temporal"}, regions, labels)
    assert math.isclose(geo["frontal"]["coverage"], 30 / 50)
    assert math.isclose(rr.agreement(ref, {"A": "frontal", "B": "temporal"}), 0.5)


def test_resolve_request_and_mesh_mismatch():
    regions, labels = _strip()
    expanded, evidence, error = rr.resolve_request("frontal", regions, labels,
                                                   provenance={"mesh": "fsaverage"})
    assert error is None and expanded == ["A", "B"]
    assert evidence["kind"] == "region_overlap" and evidence["provenance"]["mesh"] == "fsaverage"
    _, _, error = rr.resolve_request("occipital", regions, labels)
    assert error
    try:
        rr.resolve(regions[:-1], labels)
    except ValueError as exc:
        assert "different meshes" in str(exc)
    else:
        raise AssertionError("mesh mismatch not rejected")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
