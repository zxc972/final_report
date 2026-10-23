"""Round 15: CSP product matching (algorithm 3) and AND-OR backward planning (algorithm 4)."""
import importlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
KNOWLEDGE = ROOT / "knowledge_analysis"


def _load(name):
    try:
        from test_analysis_agent import agent
        return importlib.import_module(agent.__package__ + "." + name)
    except Exception:
        if "_r15m" not in sys.modules:
            pkg = types.ModuleType("_r15m")
            pkg.__path__ = [str(BACKEND)]
            sys.modules["_r15m"] = pkg
        for mod_name in ("analysis_csp_matching", name):
            full = f"_r15m.{mod_name}"
            if full not in sys.modules:
                spec = importlib.util.spec_from_file_location(full, BACKEND / f"{mod_name}.py")
                mod = importlib.util.module_from_spec(spec)
                sys.modules[full] = mod
                spec.loader.exec_module(mod)
        return sys.modules[f"_r15m.{name}"]


csp = _load("analysis_csp_matching")
andor = _load("analysis_andor_planner")

TYPES = [{"id": "P", "parent": None}, {"id": "Metric", "parent": "P"}, {"id": "Thickness", "parent": "Metric"},
         {"id": "Sulc", "parent": "Metric"}, {"id": "Annot", "parent": "P"}, {"id": "Label", "parent": "P"},
         {"id": "T1", "parent": "P"}, {"id": "Surf", "parent": "P"}]
H = csp.TypeHierarchy(TYPES)


def prod(pid, ptype, **attrs):
    return {"id": pid, "type": ptype, "attrs": attrs}


ROI_SLOTS = [{"name": "S1", "type": "Thickness"},
             {"name": "S2", "type": "Annot", "unary": [{"kind": "attr_in", "attr": "atlas", "values": ["DKT"]}]},
             {"name": "S3", "type": "Label"}]
ROI_CONSTRAINTS = [{"kind": "attr_equal", "slots": ["S1", "S2", "S3"], "attrs": ["subject", "hemisphere", "mesh"]}]


def roi_products():
    out = []
    for s in ("a", "b"):
        for h in ("lh", "rh"):
            out += [prod(f"{s}{h}.thk", "Thickness", subject=s, hemisphere=h, mesh=100),
                    prod(f"{s}{h}.sulc", "Sulc", subject=s, hemisphere=h, mesh=100),
                    prod(f"{s}{h}.dkt", "Annot", subject=s, hemisphere=h, mesh=100, atlas="DKT"),
                    prod(f"{s}{h}.a2009s", "Annot", subject=s, hemisphere=h, mesh=100, atlas="Destrieux"),
                    prod(f"{s}{h}.cortex", "Label", subject=s, hemisphere=h, mesh=100)]
    return out


def test_subsumption():
    assert H.subsumes("Metric", "Thickness") and H.subsumes("P", "Sulc")
    assert not H.subsumes("Thickness", "Sulc") and not H.subsumes("Thickness", "Unknown")


def test_csp_enumerates_consistent_assignments_only():
    out = csp.solve(ROI_SLOTS, roi_products(), ROI_CONSTRAINTS, H)
    assert out["missing"] == [] and len(out["solutions"]) == 4
    for sol in out["solutions"]:
        ids = sol["assignment"]
        prefix = ids["S1"].split(".")[0]
        assert ids["S2"] == prefix + ".dkt" and ids["S3"] == prefix + ".cortex"
    assert out["domain_sizes"] == {"S1": 4, "S2": 4, "S3": 4}


def test_csp_matches_brute_force_on_random_instances():
    rng = random.Random(15)
    for _ in range(60):
        products = []
        for i in range(rng.randint(3, 9)):
            t = rng.choice(["Thickness", "Sulc", "Annot", "Label"])
            products.append(prod(f"p{i}", t, subject=rng.choice("ab"), hemisphere=rng.choice(["lh", "rh"]),
                                 mesh=rng.choice([100, 200]), atlas=rng.choice(["DKT", "Destrieux"])))
        got = {tuple(sorted(s["assignment"].items())) for s in csp.solve(ROI_SLOTS, products, ROI_CONSTRAINTS, H)["solutions"]}
        ref = {tuple(sorted(s.items())) for s in csp.brute_force(ROI_SLOTS, products, ROI_CONSTRAINTS, H)}
        assert got == ref


def test_csp_reports_missing_typed_requirement():
    products = [p for p in roi_products() if p["type"] != "Label"]
    out = csp.solve(ROI_SLOTS, products, ROI_CONSTRAINTS, H)
    assert out["solutions"] == [] and out["missing"][0]["slot"] == "S3" and out["missing"][0]["type"] == "Label"


def test_csp_mesh_mismatch_has_no_solution_and_soft_ranking():
    products = [prod("t", "Thickness", subject="a", hemisphere="lh", mesh=100),
                prod("d", "Annot", subject="a", hemisphere="lh", mesh=200, atlas="DKT"),
                prod("c", "Label", subject="a", hemisphere="lh", mesh=100)]
    assert csp.solve(ROI_SLOTS, products, ROI_CONSTRAINTS, H)["solutions"] == []
    soft = [{"kind": "attr_equal", "slots": ["S1", "S2", "S3"], "attrs": ["subject", "hemisphere"]},
            {"kind": "attr_equal", "slots": ["S1", "S2"], "attrs": ["mesh"], "severity": "soft"}]
    out = csp.solve(ROI_SLOTS, products, soft, H)
    assert len(out["solutions"]) == 1 and out["solutions"][0]["soft_violations"] == 1


# ------------------------------------------------------------ AND-OR planning

STEPS = [
    {"id": "recon", "inputs": [{"type": "T1", "attrs": {}}],
     "outputs": [{"type": "Surf", "set": {"space": "native"}, "inherit": ["subject", "species"]},
                 {"type": "Thickness", "set": {"space": "native"}, "inherit": ["subject", "species"]}],
     "software": ["recon-all"], "species_allowed": ["macaque"], "cost": 3},
    {"id": "to_fslr", "inputs": [{"type": "Surf", "attrs": {"space": "native"}},
                                 {"type": "Thickness", "attrs": {"space": "native"}}],
     "outputs": [{"type": "Thickness", "set": {"space": "fsLR_32k"}, "inherit": ["subject", "species"]}],
     "software": ["wb_command"], "species_allowed": ["macaque"], "cost": 1},
    {"id": "lgi", "inputs": [{"type": "Surf", "attrs": {}}],
     "outputs": [{"type": "Metric", "set": {"measure": "lgi"}, "inherit": ["subject", "species"]}],
     "software": ["matlab"], "cost": 1},
]


def test_plan_reuses_existing_products_and_counts_shared_steps_once():
    have = [prod("t1", "T1", subject="a", species="macaque"),
            prod("s", "Surf", subject="a", species="macaque", space="native"),
            prod("th", "Thickness", subject="a", species="macaque", space="native")]
    target = {"type": "Thickness", "attrs": {"subject": "a", "space": "fsLR_32k"}}
    out = andor.plan([target], have, STEPS, H)
    assert out["feasible"] and out["steps"] == ["to_fslr"] and out["cost"] == 1
    fresh = andor.plan([target, {"type": "Surf", "attrs": {"subject": "a", "space": "native"}}],
                       have[:1], STEPS, H)
    assert fresh["steps"] == ["recon", "to_fslr"] and fresh["cost"] == 4
    exact = andor.optimal_plan([target], have[:1], STEPS, H)
    assert exact["cost"] == fresh["cost"]


def test_plan_reports_software_and_species_reasons():
    have = [prod("s", "Surf", subject="a", species="macaque", space="native")]
    out = andor.plan([{"type": "Metric", "attrs": {"subject": "a", "measure": "lgi"}}], have, STEPS, H,
                     software={"matlab": False})
    assert not out["feasible"] and any("matlab" in r for r in out["per_target"][0]["reasons"])
    human = [prod("t1", "T1", subject="h", species="human")]
    out = andor.plan([{"type": "Thickness", "attrs": {"subject": "h", "species": "human"}}], human, STEPS, H)
    assert not out["feasible"] and any("species human" in r for r in out["per_target"][0]["reasons"])


def test_plan_on_registered_workflow_matches_exact_optimum():
    types_doc = json.loads((KNOWLEDGE / "product_types.json").read_text())
    workflow = json.loads((KNOWLEDGE / "workflow_steps.json").read_text())
    hierarchy = csp.TypeHierarchy.from_document(types_doc)
    steps = andor.steps_from_workflow(workflow)
    assert len(steps) == 14
    t1 = [{"id": "t1", "type": "type:Volume.T1", "attrs": {"subject": "m1", "species": "macaque"}}]
    for target_type in ("type:SurfaceMetric.Thickness", "type:Annotation.AparcDK", "type:Surface.Pial"):
        target = {"type": target_type, "attrs": {"subject": "m1"}}
        greedy = andor.plan([target], t1, steps, hierarchy, software={"matlab": False})
        exact = andor.optimal_plan([target], t1, steps, hierarchy, software={"matlab": False})
        assert greedy["feasible"] == exact["feasible"]
        if exact["feasible"]:
            assert greedy["cost"] >= exact["cost"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
