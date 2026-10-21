"""Synthetic constraint observations: no models, software pipelines or real data."""

import importlib
import json

import pytest

from test_analysis_agent import agent
from test_analysis_knowledge_profiles import make_tools

c = importlib.import_module(agent.__package__ + ".analysis_constraints")
w = importlib.import_module(agent.__package__ + ".analysis_profile_worker")


def f(value, path="/inputs/0/fixture", method="synthetic fixture"):
    return w.field(value, path, method)


def file(path="/inputs/0/lh.pial", kind="surface", **fields):
    result = {
        "path": f(path),
        "format": f(kind),
        "sha256": f("a" * 64),
        "volume": f(None),
        "surface": f(None),
        "label": f(None),
        "recon": f(None),
        "subject": f(None),
    }
    result.update(fields)
    return result


def profile(files):
    return {
        "schema_version": "primatex.data_profile.v1",
        "files": files,
        "physical_scale_verified": f(None),
    }


def context(paths):
    return {
        "question": "Synthetic descriptive surface analysis",
        "data": {"files": paths, "subjects": ["fixture"]},
        "atlas": {
            "name": "none",
            "version": "none",
            "space": "stored",
            "hemisphere_rule": "separate",
        },
        "method": {
            "method_id": "self:synthetic",
            "reason": "Synthetic engineering fixture",
            "required_software": [],
        },
        "outputs": ["summary.json"],
        "code_path": "/work/analysis.py",
        "analysis_scope": {"inference": False, "scale_policy": "within_input_only"},
    }


def test_recon_fatal_and_missing_log_block():
    row = file(recon=f({"done": f(True), "fatal_count": f(1), "fatal_lines": f([2])}))
    assert c.recon_complete([row], {}, {})[0] is False
    row["recon"]["value"]["fatal_count"] = f(None)
    assert c.recon_complete([row], {}, {})[0] is False
    row["recon"]["value"]["fatal_count"] = f(0)
    assert c.recon_complete([row], {}, {})[0] is True


def test_minus_one_and_unknown_require_explicit_exclusion():
    row = file(
        kind="annot",
        label=f({"unassigned_vertices": f(2), "special_vertices": f({"unknown": 1})}),
    )
    assert c.unassigned_labels_excluded([row], {"atlas": {}}, {})[0] is False
    assert (
        c.unassigned_labels_excluded(
            [row], {"atlas": {"exclude_labels": [-1, "unknown"]}}, {}
        )[0]
        is True
    )


@pytest.mark.parametrize(
    "size,provenance,expected", [(4, True, False), (3, False, False), (3, True, True)]
)
def test_mesh_length_alone_never_establishes_space(size, provenance, expected):
    surface = file(surface=f({"vertex_count": f(3)}))
    annotation = file(
        "/inputs/0/lh.aparc.annot", "annot", label=f({"vertex_count": f(size)})
    )
    record = file("/inputs/0/registration.json", "unknown")
    plan = {
        "atlas": {
            "mesh_bindings": [
                {
                    "label": annotation["path"]["value"],
                    "surface": surface["path"]["value"],
                    "mesh_origin": "synthetic-subject native mesh",
                    "space": "synthetic",
                    "registration_ref": (
                        record["path"]["value"] if provenance else "missing"
                    ),
                }
            ]
        }
    }
    assert c.mesh_label_match([surface, annotation, record], plan, {})[0] is expected


def test_mixed_native_and_scaled_copy_blocks_pooling():
    files = [file("/inputs/0/native/lh.pial"), file("/inputs/0/subject_1mm/lh.pial")]
    assert c.scale_consistent(files, {"analysis_scope": {}}, {})[0] is False
    assert (
        c.scale_consistent(
            files, {"analysis_scope": {"scale_policy": "dimensionless_per_input"}}, {}
        )[0]
        is True
    )


def test_affine_conflict_blocks_even_if_model_claims_same_scale():
    row = file(volume=f({"units": f("mm"), "qform_sform_conflict": f(True)}))
    assert (
        c.scale_consistent(
            [row], {"analysis_scope": {"scale_policy": "within_input_only"}}, {}
        )[0]
        is False
    )


def test_one_independent_subject_and_repeated_scans_block_inference(tmp_path):
    table = tmp_path / "participants.tsv"
    table.write_text(
        "participant_id\tsession_id\nsub-one\t1\nsub-one\t2\n", encoding="utf-8"
    )
    row = w.profile_file(table)
    ctx = {
        "analysis_scope": {
            "inference": True,
            "groups": {"one": ["sub-one", "sub-one"]},
            "design_columns": 1,
        }
    }
    passed, observed = c.group_inference_sample(
        [row], ctx, {"minimum_independent_subjects": 2}
    )
    assert passed is False
    assert observed["observed_independent_subjects"] == ["sub-one"]
    assert observed["residual_dof"] == 0


def test_group_minimum_and_degrees_of_freedom():
    row = file(subject=f(["a", "b", "c", "d"]))
    plan = {
        "analysis_scope": {
            "inference": True,
            "groups": {"A": ["a", "b"], "B": ["c", "d"]},
            "design_columns": 2,
        }
    }
    assert c.group_inference_sample([row], plan, {})[0] is True
    plan["analysis_scope"]["design_columns"] = 4
    assert c.group_inference_sample([row], plan, {})[0] is False


def test_lgi_missing_matlab_tool_observation_overrides_model(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, "method_graph")
    row = file(recon=f({"done": f(True), "fatal_count": f(0), "fatal_lines": f([])}))
    tools.control_store.save("data_profile", profile([row]))
    tools._method_graph_store = type(
        "Graph",
        (),
        {"read": lambda self, mid: {"method": {"conditions": [], "inputs": []}}},
    )()

    def run(script, timeout_seconds=120, frozen_source=None):
        assert "subprocess.run" in frozen_source.read_text(encoding="utf-8")
        data = {
            "commands": [
                {
                    "command": "matlab",
                    "executable": False,
                    "exit_code": None,
                    "locations": [],
                },
                {"command": "recon-all", "executable": True, "exit_code": 0},
            ]
        }
        return {
            "status": "success",
            "exit_code": 0,
            "stdout": "PRIMATEX_CONSTRAINT_PROBE=" + json.dumps(data),
        }

    tools.executor.run = run
    plan = context([row["path"]["value"]])
    result = tools.compile_constraints(
        "method:v12:local_gyrification", "lgi", plan, {"software_available": "pass"}
    )
    assert result["status"] == "blocked"
    software = next(
        row for row in result["rows"] if row["constraint_id"] == "software_available"
    )
    assert (
        software["verdict"] == "block"
        and software["agreement"] is False
        and software["conflict"] is True
    )
    assert (
        tools.control_store.latest("constraints")["sha256"]
        == result["constraints_sha256"]
    )
    (tools.workdir / "constraints.json").write_text('{"rows":[]}', encoding="utf-8")
    assert tools.control_store.latest("constraints")["record"]["summary"]["block"] == 1


def test_unmapped_conditions_remain_unverified(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, "method_graph")
    row = file()
    tools.control_store.save("data_profile", profile([row]))
    tools._method_graph_store = type(
        "Graph",
        (),
        {
            "read": lambda self, mid: {
                "method": {
                    "inputs": [],
                    "conditions": [
                        {"id": "unmapped", "statement": "Synthetic unmapped fact"}
                    ],
                }
            }
        },
    )()
    monkeypatch.setattr(
        c, "software_observation", lambda *args: (True, {"commands": []})
    )
    result = tools.compile_constraints(
        "method:v13:global_convex_hull_gyrification",
        "geometry",
        context([row["path"]["value"]]),
        {"unmapped": "pass"},
    )
    assert result["unmapped_conditions"][0]["status"] == "unverified"
    assert result["summary"]["warn"] == 1


def test_unmapped_software_is_not_a_hard_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, "method_graph")
    row = file()
    tools.control_store.save("data_profile", profile([row]))
    plan = context([row["path"]["value"]])
    del plan["method"]["required_software"]
    result = tools.compile_constraints("self:synthetic", "geometry", plan)
    software = next(
        row for row in result["rows"] if row["constraint_id"] == "software_available"
    )
    assert software["verdict"] == "block"
    assert software["tool_observed"]["status"] == "unverified"


def test_annotation_observation_triggers_constraints_despite_task_label(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, "method_graph")
    monkeypatch.setattr(
        c, "software_observation", lambda *args: (True, {"scope": "synthetic fixture"})
    )
    row = file(
        "/inputs/0/lh.annot",
        "annot",
        label=f(
            {
                "vertex_count": f(3),
                "unassigned_vertices": f(1),
                "special_vertices": f({"unknown": 0}),
            }
        ),
    )
    tools.control_store.save("data_profile", profile([row]))
    plan = context([row["path"]["value"]])
    result = tools.compile_constraints("self:synthetic", "geometry", plan)
    by_id = {item["constraint_id"]: item for item in result["rows"]}
    assert result["derived_task_categories"] == ["roi"]
    assert by_id["unassigned_labels_excluded"]["verdict"] == "block"
    assert by_id["mesh_label_match"]["verdict"] == "block"


def test_roi_method_with_no_annotation_does_not_pass_mesh_check():
    ok, observed = c.mesh_label_match(
        [file()], {"method": {"method_id": "method:v12:surface_annotation_roi"}}, {}
    )
    assert ok is False and observed["annotation_present"] is False
