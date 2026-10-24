"""Real synthetic FreeSurfer inputs: region evidence, sealing and host checks."""
import copy
import hashlib
import importlib
import json
import struct
from pathlib import Path
import pytest
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products, p

lobes = importlib.import_module(agent.__package__ + ".analysis_lobar_mapping")
overlap = importlib.import_module(agent.__package__ + ".analysis_region_overlap")
numeric = importlib.import_module(agent.__package__ + ".analysis_independent_numeric")
worker = importlib.import_module(agent.__package__ + ".analysis_profile_worker")


def annot(path, names, labels):
    colors = [(0, 0, 0), (10, 20, 30), (40, 50, 60)]
    packed = [r + (g << 8) + (b << 16) for r, g, b in colors]
    def string(value):
        raw = value.encode() + b"\0"
        return struct.pack(">i", len(raw)) + raw
    raw = struct.pack(">i", len(labels))
    raw += b"".join(struct.pack(">ii", index, packed[label]) for index, label in enumerate(labels))
    raw += struct.pack(">ii", 1, len(names)) + string("synthetic-only")
    for name, color in zip(names, colors):
        raw += string(name) + struct.pack(">iiii", *color, 0)
    path.write_bytes(raw)


def fixture(tmp_path, monkeypatch, *, qualified=True):
    tools = setup_products(tmp_path, monkeypatch)
    root = tools.input_roots[0]
    rows = []
    vertices = [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.),
                (2., 0., 0.), (3., 0., 0.), (2., 1., 0.)]
    faces = [(0, 1, 2), (3, 4, 5)]
    for hemi in ("lh", "rh"):
        ann = root / "label" / f"{hemi}.aparc.a2009s.annot"
        dk = root / "label" / f"{hemi}.aparc.annot"
        annot(dk, ["unknown", "precentral", "postcentral"], [1, 1, 1, 2, 2, 2])
        annot(ann, ["unknown", "G_A", "G_B"], [1, 1, 1, 1, 1, 2] if qualified else [1, 1, 1, 2, 2, 2])
        surf = root / "surf" / f"{hemi}.white"
        surf.write_bytes(b"\xff\xff\xfe" + b"synthetic\n\n" + struct.pack(">ii", 6, 2)
                         + b"".join(struct.pack(">fff", *v) for v in vertices)
                         + b"".join(struct.pack(">iii", *f) for f in faces))
        registration = root / "surf" / f"{hemi}.sphere.reg"
        registration.write_bytes(surf.read_bytes())
        metric = root / "surf" / f"{hemi}.thickness"
        metric.write_bytes(b"\xff\xff\xff" + struct.pack(">iii", 6, 2, 1) + struct.pack(">6f", 1., 2., 3., 4., 5., 6.))
        cortex = root / "label" / f"{hemi}.cortex.label"
        cortex.write_text("# synthetic cortex\n6\n" + "".join(f"{i} 0 0 0 0\n" for i in range(6)))
        for path in [ann, dk, surf, registration, metric, cortex]:
            item = worker.profile_file(path)
            item["path"] = worker.field("/inputs/0/" + path.relative_to(root).as_posix(), path, "synthetic mapped input")
            rows.append(item)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"roots": [{"path": str(root), "subject_id": "synthetic", "species_declared": "human", "source": "synthetic only"}]}))
    monkeypatch.setenv("AGENT_DATA_CATALOG", str(catalog))
    monkeypatch.setenv("AGENT_CROSSSPECIES_RULES", "0")
    saved = tools.control_store.save("data_profile", {"schema_version": "primatex.data_profile.v1", "files": rows, "physical_scale_verified": worker.field(None, "fixture", "not verified")})
    monkeypatch.setattr(p, "ensure_profile", lambda *args: (saved, True))
    entry = {"root": root, "index": 0, "subject_id": "synthetic", "species_declared": "human"}
    return tools, entry


def context_for(tools):
    result = p.plan_analysis(tools, {"measures": ["thickness"], "regions": "frontal lobe"})
    candidates = [c for c in result.get("candidates", []) if c["atlas"]["name"] == "aparc.a2009s"]
    assert candidates, result
    committed = p.commit_candidate(tools, candidates[0]["candidate_id"], "Synthetic overlap test only", "/work/analysis.py")
    assert committed["status"] == "committed", committed
    return tools.control_store.latest("plan")["record"]["plan"]


def test_human_a2009s_request_seals_overlap_inputs_and_reports_qualified_geometry(tmp_path, monkeypatch):
    tools, entry = fixture(tmp_path, monkeypatch)
    before = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in entry["root"].rglob("*") if f.is_file()}
    plan = context_for(tools)
    evidence = plan["analysis_scope"]["region_overlap_evidence"]
    assert len(evidence) == 2
    assert plan["data"]["species_declared"] == "human"
    for row in evidence:
        assert row["kind"] == "region_overlap" and row["verdict"] == "qualified"
        assert row["coverage"] == 1.0 and row["purity"] == .6
        assert row["parameters"] == {"theta": .5, "kappa": .8, "pi": .8, "tau": .2, "weighted": True}
        assert {r["path"] for r in row["provenance"]["inputs"].values()} <= set(plan["data"]["files"])
        assert all(len(r["sha256"]) == 64 for r in row["provenance"]["inputs"].values())
    assert any("coverage=1.000000, purity=0.600000" in n for n in plan["analysis_scope"]["notices"])
    assert before == {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in entry["root"].rglob("*") if f.is_file()}


@pytest.mark.parametrize("missing", ["label/lh.aparc.annot", "surf/lh.white"])
def test_missing_reference_annotation_or_white_is_reported(tmp_path, monkeypatch, missing):
    tools, entry = fixture(tmp_path, monkeypatch)
    (entry["root"] / missing).unlink()
    labels, evidence, error = lobes.resolve_lobes(entry, "aparc.a2009s", "frontal lobe", ["G_A", "G_B"], tools=tools, hemisphere="lh", annotation_path="/inputs/0/label/lh.aparc.a2009s.annot")
    assert not evidence and "Missing region overlap product" in error and Path(missing).name in error


def test_nonhuman_lobar_request_never_reads_geometry(tmp_path, monkeypatch):
    tools, entry = fixture(tmp_path, monkeypatch)
    entry["species_declared"] = "macaque"
    monkeypatch.setattr(overlap, "resolve_native", lambda *a, **k: pytest.fail("Nonhuman geometry must not be entered"))
    _, evidence, error = lobes.resolve_lobes(entry, "aparc.a2009s", "frontal lobe", ["G_A", "G_B"], tools=tools, hemisphere="lh", annotation_path="/inputs/0/label/lh.aparc.a2009s.annot")
    assert not evidence and "CHARM" in error and "human-named aparc" in error


def test_shared_host_recomputation_checks_geometry_and_fingerprints(tmp_path, monkeypatch):
    tools, entry = fixture(tmp_path, monkeypatch)
    plan = context_for(tools)
    mapping, digest = p.load_knowledge("lobar_mapping", tools)
    report = overlap.recheck(plan, tools.resolve, mapping["records"], digest)
    assert len(report) == 2 and all(r["status"] == "pass" and r["independent_implementation"] is False for r in report)
    altered = copy.deepcopy(plan)
    altered["analysis_scope"]["region_overlap_evidence"][0]["purity"] = .9
    with pytest.raises(ValueError, match="recomputation"):
        overlap.recheck(altered, tools.resolve, mapping["records"], digest)
    path = entry["root"] / "label/lh.aparc.annot"
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="fingerprint"):
        overlap.recheck(plan, tools.resolve, mapping["records"], digest)


def test_qualified_card_contains_coverage_purity_and_disclosure(tmp_path, monkeypatch):
    tools, entry = fixture(tmp_path, monkeypatch)
    plan = context_for(tools)
    monkeypatch.setattr(numeric, "current_summary", lambda *a: {"host_verified": True, "status": "pass"})
    card = numeric.result_card(tools, "Synthetic descriptive values; region geometry is approximate.")
    assert card["verdict"] == "qualified"
    assert all(row["coverage"] == 1.0 and row["purity"] == .6 for row in card["region_resolution"])
    assert any("coverage=1.000000, purity=0.600000" in text for text in card["required_disclosures"])


def test_geometry_on_different_mesh_is_reported_not_name_matched(tmp_path, monkeypatch):
    tools, entry = fixture(tmp_path, monkeypatch)
    annot(entry["root"] / "label/lh.aparc.annot", ["unknown", "precentral", "postcentral"], [1, 1, 2])
    _, evidence, error = lobes.resolve_lobes(entry, "aparc.a2009s", "frontal lobe", ["G_A", "G_B"], tools=tools, hemisphere="lh", annotation_path="/inputs/0/label/lh.aparc.a2009s.annot")
    assert not evidence and "share a vertex mesh" in error


def test_resolved_geometry_retains_default_thresholds(tmp_path, monkeypatch):
    tools, entry = fixture(tmp_path, monkeypatch, qualified=False)
    labels, evidence, error = lobes.resolve_lobes(entry, "aparc.a2009s", "frontal lobe", ["G_A", "G_B"], tools=tools, hemisphere="lh", annotation_path="/inputs/0/label/lh.aparc.a2009s.annot")
    assert error is None and labels == ["G_A"] and evidence[0]["verdict"] == "resolved"
    assert evidence[0]["coverage"] == evidence[0]["purity"] == evidence[0]["dice"] == 1.0
