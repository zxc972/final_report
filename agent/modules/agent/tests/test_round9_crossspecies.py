"""Known synthetic regression cases, not expert or blind validation."""

import copy
import importlib
import json

import pytest
from test_analysis_agent import agent
from test_round8_closure import sealed
from test_analysis_knowledge_profiles import make_tools, capture_builder

c = importlib.import_module(agent.__package__ + ".analysis_crossspecies")
t = importlib.import_module(agent.__package__ + ".analysis_crossspecies_templates")
params = {
    row["template"]: row["parameters"]
    for row in c.load_policy("cross_species_rules")["templates"]
}


@pytest.mark.parametrize(
    "name,good,bad",
    [
        (
            "species_atlas",
            {"species": ["macaque"], "atlas": {"name": "CHARM", "tissue": "cortical"}},
            {"species": ["macaque"], "atlas": {"name": "DK"}},
        ),
        (
            "homology_evidence",
            {
                "cross_species": True,
                "homology": [
                    {
                        "host_verified": True,
                        "kind": "cited_correspondence",
                        "source_url": "https://example.org/paper",
                        "mapping_sha256": "a" * 64,
                        "scope_matches": True,
                    }
                ],
            },
            {"cross_species": True},
        ),
        (
            "scale_check",
            {
                "scale": {"rescaled": True, "host_verified": True, "k": 2},
                "measurements": [
                    {"metric": "surface_area", "stored_value": 400, "value": 100}
                ],
            },
            {
                "scale": {"rescaled": True, "host_verified": True, "k": 2},
                "measurements": [
                    {"metric": "surface_area", "stored_value": 400, "value": 400}
                ],
            },
        ),
        (
            "plausibility",
            {
                "measurements": [
                    {
                        "species": "macaque",
                        "metric": "thickness",
                        "scope": "whole_cortex_mean",
                        "unit": "mm",
                        "value": 2.1,
                        "physical_scale_verified": True,
                    }
                ]
            },
            {
                "measurements": [
                    {
                        "species": "macaque",
                        "metric": "thickness",
                        "scope": "whole_cortex_mean",
                        "unit": "mm",
                        "value": 20,
                        "physical_scale_verified": True,
                    }
                ]
            },
        ),
        (
            "asymmetry_flip",
            {
                "asymmetry": True,
                "bias_checks": [
                    {
                        "kind": "flip_test",
                        "host_verified": True,
                        "passed": True,
                        "evidence_ref": "fixture",
                    }
                ],
            },
            {"asymmetry": True},
        ),
        (
            "cross_species_measure",
            {
                "cross_species": True,
                "species": ["human", "macaque"],
                "measure_kind": "ratio",
            },
            {
                "cross_species": True,
                "species": ["human", "macaque"],
                "measure_kind": "absolute_thickness",
            },
        ),
        (
            "min_detectable_effect",
            {
                "group_inference": True,
                "groups": {
                    "A": ["a" + str(i) for i in range(100)],
                    "B": ["b" + str(i) for i in range(100)],
                },
                "negative_result": True,
            },
            {
                "group_inference": True,
                "groups": {"A": ["a"], "B": ["b"]},
                "negative_result": True,
            },
        ),
    ],
)
def test_each_new_template_pass_and_adverse(name, good, bad):
    refs = c.load_policy("species_reference_values")["references"]
    fn = t.CHECKERS[name]
    assert fn(params[name], {**good, "references": refs})["verdict"] == "pass"
    assert fn(params[name], {**bad, "references": refs})["verdict"] in {"warn", "block"}


@pytest.mark.parametrize(
    "verdict,index",
    [
        (v, i)
        for v in ["accepted", "qualified", "revised", "blocked", "rejected", "deferred"]
        for i in range(2)
    ],
)
def test_two_cases_per_conclusion_verdict(verdict, index):
    checks = [{"constraint_id": "fixture", "severity": "hard", "verdict": "pass"}]
    observed = {
        "independent_numeric": {
            "host_verified": True,
            "status": "pass",
            "evidence_ref": "private-fixture",
        }
    }
    scope = "supplied_descriptive"
    direction = None
    if verdict == "qualified":
        checks.append(
            {
                "constraint_id": "warn",
                "severity": "soft",
                "verdict": "warn",
                "tool_observed": {
                    "reason": "Fixture warning",
                    "conclusion_ceiling": "qualified" if index else None,
                },
            }
        )
    elif verdict == "revised":
        scope = "group_inference" if index else "cross_species_homology"
    elif verdict == "blocked":
        if index:
            observed["independent_numeric"]["status"] = "fail"
        else:
            checks.append(
                {
                    "constraint_id": "mandatory",
                    "severity": "hard",
                    "verdict": "block",
                    "mandatory": True,
                }
            )
    elif verdict == "rejected":
        observed["observed_direction"] = {
            "host_verified": True,
            "direction": "positive" if index else "negative",
            "evidence_ref": "fixture",
        }
        direction = "negative" if index else "positive"
    elif verdict == "deferred":
        if index:
            checks.append(
                {
                    "constraint_id": "power",
                    "severity": "soft",
                    "verdict": "warn",
                    "tool_observed": {"underpowered_negative": True},
                }
            )
        else:
            observed = {}
    card = c.conclusion_card(
        "Fixed offline placeholder; no real finding.",
        scope,
        checks,
        observed,
        ["supplied_descriptive"],
        direction=direction,
    )
    assert card["verdict"] == verdict
    assert card["must_rewrite"] == (verdict == "revised")
    assert card["prose_semantic_entailment"].startswith("not_certified")


def test_rewrite_changes_scope_without_erasing_old_card():
    checks = [{"constraint_id": "fixture", "severity": "hard", "verdict": "pass"}]
    evidence = {"independent_numeric": {"host_verified": True, "status": "pass"}}
    first = c.conclusion_card(
        "Synthetic group claim",
        "group_inference",
        checks,
        evidence,
        ["supplied_descriptive"],
    )
    second = c.conclusion_card(
        "Rewritten supplied-data description",
        "supplied_descriptive",
        checks,
        evidence,
        ["supplied_descriptive"],
    )
    assert first["verdict"] == "revised" and second["verdict"] == "accepted"
    assert first["conclusion_text"] == "Synthetic group claim"


@pytest.mark.parametrize(
    "field", ["success_criteria", "failure_criteria", "species", "scale_status"]
)
def test_commitment_rejects_missing_fields(field):
    v = {
        "success_criteria": "All declared outputs and independent checks pass",
        "failure_criteria": "Any mandatory mismatch",
        "species": ["macaque"],
        "scale_status": "unknown",
    }
    del v[field]
    with pytest.raises(ValueError):
        c.validate_commitment(v, {"analysis_scope": {"comparison": "describe"}})


def test_cross_commitment_needs_homology():
    with pytest.raises(ValueError, match="homology_evidence"):
        c.validate_commitment(
            {
                "success_criteria": "pass",
                "failure_criteria": "fail",
                "species": ["human", "macaque"],
                "scale_status": "unknown",
            },
            {"analysis_scope": {"comparison": "cross_species"}},
        )


def test_repeats_do_not_increase_n_or_cross_group_independence():
    result = t.min_detectable_effect(
        params["min_detectable_effect"],
        {
            "group_inference": True,
            "groups": {"A": ["a"] * 10, "B": ["b"] * 10},
            "negative_result": True,
        },
    )
    assert (
        result["evidence"]["n_per_group_conservative"] == 1
        and result["underpowered_negative"]
    )
    overlap = t.min_detectable_effect(
        params["min_detectable_effect"],
        {
            "group_inference": True,
            "groups": {"A": ["a"], "B": ["a"]},
            "negative_result": True,
        },
    )
    assert overlap["missing_required_evidence"]


def test_sd_scope_and_roi_scope_are_not_confused():
    refs = c.load_policy("species_reference_values")["references"]
    row = {
        "species": "macaque",
        "metric": "thickness",
        "scope": "whole_cortex_mean",
        "sampling_scope": "individual_mean",
        "unit": "mm",
        "value": 2.1,
        "physical_scale_verified": True,
    }
    result = t.plausibility(
        params["plausibility"], {"measurements": [row], "references": refs}
    )
    assert result["evidence"]["comparisons"][0]["z"] is None
    row["scope"] = "prefrontal_roi"
    assert (
        t.plausibility(
            params["plausibility"], {"measurements": [row], "references": refs}
        )["verdict"]
        == "warn"
    )


def test_loglog_two_species_is_blocked_but_three_permitted():
    env = {
        "cross_species": True,
        "species": ["human", "macaque"],
        "measure_kind": "loglog_residual",
    }
    assert (
        t.cross_species_measure(params["cross_species_measure"], env)["verdict"]
        == "block"
    )
    assert (
        t.cross_species_measure(
            params["cross_species_measure"],
            {**env, "species": ["human", "macaque", "chimpanzee"]},
        )["verdict"]
        == "pass"
    )


def test_atlas_bindings_are_checked_per_species_and_tissue():
    env = {
        "species": ["human", "macaque"],
        "atlas_bindings": [
            {"species": "human", "atlas": {"name": "DK"}},
            {"species": "macaque", "atlas": {"name": "CHARM"}},
        ],
    }
    assert t.species_atlas(params["species_atlas"], env)["verdict"] == "pass"
    assert (
        t.species_atlas(
            params["species_atlas"],
            {"species": ["macaque"], "atlas": {"name": "SARM", "tissue": "cortical"}},
        )["verdict"]
        == "block"
    )


def test_c_disabled_and_legacy_prompt_are_unchanged(tmp_path, monkeypatch):
    from test_analysis_knowledge_profiles import policy

    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, "legacy_v13")
    before = capture_builder(tools, monkeypatch)["system_prompt"]
    monkeypatch.setenv("AGENT_CROSSSPECIES_RULES", "1")
    after = capture_builder(tools, monkeypatch)["system_prompt"]
    assert before == after and len(after.encode()) == 7652
    assert not c.enabled(tools)


def test_compiler_appends_seven_host_observations_only_when_enabled(
    tmp_path, monkeypatch
):
    tools, _, committed = sealed(tmp_path, monkeypatch)
    compiler = importlib.import_module(agent.__package__ + ".analysis_constraints")
    before = compiler.compile_constraints(
        tools,
        committed["plan"]["method"]["method_id"],
        "descriptive",
        committed["plan"],
    )
    assert not any(row["constraint_id"].startswith("cross:") for row in before["rows"])
    monkeypatch.setenv("AGENT_CROSSSPECIES_RULES", "1")
    after = compiler.compile_constraints(
        tools,
        committed["plan"]["method"]["method_id"],
        "descriptive",
        committed["plan"],
    )
    added = [row for row in after["rows"] if row["constraint_id"].startswith("cross:")]
    assert len(added) == 7
    assert (
        next(row for row in added if row["template"] == "scale_check")["severity"]
        == "soft"
    )


def test_enabled_commit_seals_agent_criteria_and_keeps_versions(tmp_path, monkeypatch):
    tools, candidate, first = sealed(tmp_path, monkeypatch)
    catalogue = tmp_path / "catalog.json"
    subject = first["plan"]["data"]["subjects"][0]
    catalogue.write_text(
        json.dumps(
            {
                "roots": [
                    {
                        "path": str(tools.input_roots[0]),
                        "subject_id": subject,
                        "species_declared": "human",
                        "source": "Explicit synthetic registration",
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("AGENT_DATA_CATALOG", str(catalogue))
    monkeypatch.setenv("AGENT_CROSSSPECIES_RULES", "1")
    planner = importlib.import_module(agent.__package__ + ".analysis_product_planner")
    commitment = {
        "success_criteria": "Outputs and independent checks pass",
        "failure_criteria": "Any mandatory mismatch",
        "species": ["human"],
        "scale_status": "unknown",
        "homology_evidence": [],
    }
    committed = planner.commit_candidate(
        tools,
        candidate["candidate_id"],
        "Synthetic criteria fixture",
        "/work/resealed.py",
        commitment,
    )
    assert committed["status"] == "committed", committed
    assert committed["version"] == first["version"] + 1
    assert committed["plan"]["analysis_scope"]["commitment"] == commitment
    bundle = json.loads(
        tools.resolve(committed["execution_bundle"]["bundle_ref"]).read_text()
    )
    assert bundle["commitment"] == commitment
    assert len(tools.control_store.versions("plan")) == 2


def test_three_sigma_only_uses_a_comparable_sd():
    ref = {
        "id": "synthetic-reference",
        "species": "macaque",
        "metric": "thickness",
        "scope": "whole_cortex_mean",
        "unit": "mm",
        "mean": 2.1,
        "sd": 0.1,
        "sd_scope": "individual_mean",
        "source": {"fixture": True},
    }
    row = {
        "species": "macaque",
        "metric": "thickness",
        "scope": "whole_cortex_mean",
        "sampling_scope": "individual_mean",
        "unit": "mm",
        "value": 2.5,
        "physical_scale_verified": True,
    }
    response = t.plausibility(
        params["plausibility"], {"measurements": [row], "references": [ref]}
    )
    assert response["verdict"] == "warn"
    assert response["evidence"]["comparisons"][0]["z"] > 3
    assert response["evidence"]["comparisons"][0]["relative_deviation"] < 0.5


def test_revised_card_forces_rewrite_before_final_reply(tmp_path, monkeypatch):
    from langchain.agents.middleware import ModelRequest
    from langchain_core.tools import StructuredTool
    from test_round8_closure import fake_execution

    tools, _, _ = sealed(tmp_path, monkeypatch)
    fake_execution(tools)
    tools.write_code("/work/analysis.py", "print('fixture')")
    tools.run_python()
    monkeypatch.setenv("AGENT_CROSSSPECIES_RULES", "1")
    phase = importlib.import_module(agent.__package__ + ".analysis_phase_tools")

    catalogue = tmp_path / "rewrite_catalog.json"
    catalogue.write_text(
        json.dumps(
            {
                "roots": [
                    {
                        "path": str(tools.input_roots[0]),
                        "subject_id": tools.control_store.latest("plan")["record"][
                            "plan"
                        ]["data"]["subjects"][0],
                        "species_declared": "human",
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("AGENT_DATA_CATALOG", str(catalogue))

    def submit_conclusion(text: str, claim_scope: str):
        """Offline conclusion fixture."""
        return c.submit_conclusion(tools, text, claim_scope)

    request = ModelRequest(
        model=None, messages=[], tools=[StructuredTool.from_function(submit_conclusion)]
    )
    assert (
        phase.restrict_request(tools, request).tool_choice["function"]["name"]
        == "submit_conclusion"
    )
    tools.control_store.save(
        "crossspecies_observations",
        {
            "plan_sha256": tools.control_store.latest("plan")["sha256"],
            "execution_receipt_id": tools.last_execution["receipt_id"],
            "independent_numeric": {
                "host_verified": True,
                "status": "pass",
                "evidence_ref": "synthetic reference",
            },
        },
    )
    first = c.submit_conclusion(tools, "Synthetic overclaim", "group_inference")
    assert first["conclusion_card"]["verdict"] == "revised"
    assert (
        phase.restrict_request(tools, request).tool_choice["function"]["name"]
        == "submit_conclusion"
    )
    second = c.submit_conclusion(
        tools, "Supplied synthetic observations only", "supplied_descriptive"
    )
    assert second["conclusion_card"]["verdict"] == "qualified"
    assert phase.restrict_request(tools, request).tool_choice is None
    assert len(tools.control_store.versions("conclusion")) == 2


def test_late_negative_result_rechecks_power_before_conclusion(tmp_path, monkeypatch):
    from test_round8_closure import fake_execution

    tools, _, _ = sealed(tmp_path, monkeypatch)
    fake_execution(tools)
    tools.write_code("/work/analysis.py", "print('fixture')")
    tools.run_python()
    monkeypatch.setenv("AGENT_CROSSSPECIES_RULES", "1")
    environment = {
        "species": ["human"],
        "atlas": {"name": "DK"},
        "group_inference": True,
        "groups": {
            "A": ["a1", "a2", "a3", "a4", "a5"],
            "B": ["b1", "b2", "b3", "b4", "b5"],
        },
        "negative_result": True,
        "independent_numeric": {
            "host_verified": True,
            "status": "pass",
            "evidence_ref": "synthetic late result",
        },
    }
    monkeypatch.setattr(c, "observed_environment", lambda *args: environment)
    result = c.submit_conclusion(
        tools, "Fixed negative-result placeholder", "supplied_descriptive"
    )
    assert result["conclusion_card"]["verdict"] == "deferred"
    power = next(
        row
        for row in result["conclusion_card"]["checks_not_passed"]
        if row["constraint_id"] == "cross:min_detectable_effect"
    )
    assert power["tool_observed"]["evidence"]["d_min"] > 0.8
    assert (
        tools.control_store.latest("conclusion_checks")["record"][
            "execution_receipt_id"
        ]
        == tools.last_execution["receipt_id"]
    )


def test_supported_scope_comes_from_plan_and_sourced_rules():
    rows = [{"constraint_id": "fixture", "severity": "hard", "verdict": "pass"}]
    assert "group_inference" in c.supported_scopes(
        {"analysis_scope": {"comparison": "group"}}, rows
    )
    assert "group_inference" not in c.supported_scopes(
        {"analysis_scope": {"comparison": "describe"}}, rows
    )
    assert "cross_species_comparison" not in c.supported_scopes(
        {"analysis_scope": {"comparison": "cross_species"}}, rows
    )
    for identifier in ["cross:homology_evidence", "cross:species_atlas"]:
        rows.append(
            {"constraint_id": identifier, "severity": "hard", "verdict": "pass"}
        )
    assert "cross_species_comparison" in c.supported_scopes(
        {"analysis_scope": {"comparison": "cross_species"}}, rows
    )
    rows.append({"constraint_id": "scale", "severity": "hard", "verdict": "block"})
    assert "cross_species_comparison" not in c.supported_scopes(
        {"analysis_scope": {"comparison": "cross_species"}}, rows
    )
