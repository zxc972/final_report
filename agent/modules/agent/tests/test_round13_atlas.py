"""Canonical parcellations stay distinct; asymmetry has a public formula."""
import copy
import importlib
import pytest
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products, p
from test_analysis_constraints import f

atlas = importlib.import_module(agent.__package__ + ".analysis_atlas_identity")
asymmetry = importlib.import_module(agent.__package__ + ".analysis_asymmetry_contract")


@pytest.mark.parametrize("stem,name", [("aparc", "DK"), ("aparc.DKTatlas.mapped", "DKT"), ("aparc.a2009s", "Destrieux")])
def test_exact_source_backed_atlas(stem, name):
    observed = atlas.identify(stem)
    assert observed["canonical_name"] == name and observed["source_url"].startswith("https://")


def test_requested_dk_is_not_silently_replaced_by_dkt(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    profile = copy.deepcopy(tools.control_store.latest("data_profile")["record"])
    for row in profile["files"]:
        path = row["path"]["value"]
        if path.endswith(".aparc.annot"):
            new = path.replace(".aparc.annot", ".aparc.DKTatlas.mapped.annot")
            tools.resolve(path).rename(tools.resolve(new))
            row["path"] = f(new)
    saved = tools.control_store.save("data_profile", profile)
    monkeypatch.setattr(p, "ensure_profile", lambda tools, paths: (saved, True))
    missing = tools.plan_analysis({"measures": ["thickness"], "regions": "DK"})
    assert missing["status"] == "blocked" and not missing["candidates"]
    assert missing["available_atlases"] == ["DKT"]
    assert "Missing DK; available DKT" in missing["infeasible"][0]["reason"]
    valid = tools.plan_analysis({"measures": ["thickness"], "regions": "DKT"})
    assert valid["candidates"]
    assert {row["atlas"]["name"] for row in valid["candidates"]} == {"aparc.DKTatlas.mapped"}


def test_independent_signed_pair_asymmetry_and_missing_side():
    rows = [{"subject": "one", "metric": "thickness", "name": "region", "hemisphere": hemi, "mean": mean}
            for hemi, mean in [("lh", 4.0), ("rh", 2.0)]]
    assert asymmetry.independent_indices(rows)[("one", "thickness", "region")] == pytest.approx(2/3)
    with pytest.raises(ValueError, match="Both hemispheres"):
        asymmetry.independent_indices(rows[:1])
