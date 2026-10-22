"""Offline nine-template, unified-store and source-provenance regressions."""

import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from test_analysis_agent import agent
from test_analysis_constraints import c, file, f, profile
from test_analysis_product_planner import setup_products

t = importlib.import_module(agent.__package__ + ".analysis_condition_templates")
b = importlib.import_module(agent.__package__ + ".analysis_template_bindings")
u = importlib.import_module(agent.__package__ + ".analysis_unified_store")
i = importlib.import_module(agent.__package__ + ".analysis_product_instances")
r = importlib.import_module(agent.__package__ + ".analysis_unified_runtime")
ROOT = Path(u.__file__).parent.parent / "knowledge_analysis"


def database(tmp_path):
    store = u.UnifiedKnowledge(tmp_path / "protected" / "graph.sqlite3")
    store.import_knowledge(ROOT, None)
    return store


@pytest.mark.parametrize(
    "template,parameters,env,verdict",
    [
        (
            "product_present",
            {"slot": "x", "type": "type:Surface"},
            {
                "slots": {"x": [{"id": "s", "type": "type:Surface"}]},
                "is_subtype": lambda a, b: a == b,
            },
            "pass",
        ),
        (
            "attr_equal",
            {"slots": ["x"], "attribute": "mesh"},
            {
                "slots": {
                    "x": [{"attributes": {"mesh": 3}}, {"attributes": {"mesh": 4}}]
                }
            },
            "block",
        ),
        (
            "attr_in",
            {"slot": "x", "attribute": "space", "values": ["native"]},
            {"slots": {"x": [{"attributes": {"space": None}}]}},
            "block",
        ),
        (
            "label_policy",
            {"slot": "x"},
            {
                "slots": {
                    "x": [
                        {
                            "id": "a",
                            "attributes": {
                                "unassigned_vertices": 1,
                                "label_names": ["unknown"],
                                "label_keys": [0],
                            },
                        }
                    ]
                },
                "plan": {"atlas": {"exclude_labels": [-1, "unknown"]}},
            },
            "block",
        ),
        (
            "cardinality",
            {"object": "objects.scans", "minimum": 2},
            {"objects": {"scans": ["s1", "s1"]}},
            "block",
        ),
        (
            "design_variable",
            {"slot": "x", "variable": "age"},
            {
                "slots": {
                    "x": [
                        {
                            "id": "table",
                            "attributes": {
                                "columns": ["age"],
                                "nonempty_columns": {"age": False},
                            },
                        }
                    ]
                }
            },
            "block",
        ),
        (
            "software",
            {"commands": ["matlab"]},
            {"software": [{"command": "matlab", "executable": False}]},
            "block",
        ),
        (
            "provenance",
            {"slot": "x", "step": "rescale"},
            {"slots": {"x": [{"id": "surface"}]}, "provenance": {}},
            "block",
        ),
        ("advisory", {"text": "Physical calibration remains unverified"}, {}, "warn"),
    ],
)
def test_nine_templates(template, parameters, env, verdict):
    result = t.evaluate(
        {"id": "fixture", "template": template, "parameters": parameters}, env
    )
    assert result["verdict"] == verdict
    assert result["evidence"] is not None


def test_subtyping_dedup_and_quarantine(tmp_path):
    store = database(tmp_path)
    before = store.stats()
    store.import_knowledge(ROOT, None)
    assert before == store.stats()
    assert store.is_subtype("type:SurfaceMetric.Thickness", "type:SurfaceMetric")
    assert not store.is_subtype(
        "type:SurfaceMetric.Sulc", "type:SurfaceMetric.Thickness"
    )
    assert store.edge("missing", "type:Volume", "bad") is False
    assert store.stats()["quarantined_edges"] == 1
    assert store.integrity() == {"sqlite": "ok", "foreign_key_errors": []}
    body, sha = store.document("method_requirements")
    assert body["methods"] and len(sha) == 64
    assert set(store.stats()["nodes_by_layer"]) <= {"knowledge", "workflow", "instance"}
    assert len(store.find_nodes(layer="knowledge", kind="ProductType")) == 46
    assert store.find_nodes(kind="Condition")
    assert store.find_nodes(kind="Source")
    assert store.find_nodes(layer="workflow", kind="StepType")


def test_import_tamper_does_not_replace_document(tmp_path):
    store = database(tmp_path)
    original = store.document("product_types")
    malicious = tmp_path / "types.json"
    malicious.write_text("{}")
    with pytest.raises(ValueError, match="digest"):
        store.document("product_types", malicious, "0" * 64)
    assert store.document("product_types") == original


def test_instance_mesh_and_prov_do_not_fabricate_generation(tmp_path):
    store = database(tmp_path)
    surface = file(
        "/inputs/2/surf/lh.white",
        surface=f({"vertex_count": f(4), "face_count": f(4), "hemisphere": f("lh")}),
    )
    label = file(
        "/inputs/2/label/lh.cortex.label", "label", label=f({"vertex_count": f(2)})
    )
    result = i.import_profile(
        store,
        profile([surface, label]),
        [
            {
                "input_index": 2,
                "path": "/approved/fixture",
                "subject_id": "fixture",
                "species_declared": "monkey_unknown",
            }
        ],
    )
    nodes = [store.get_node(identifier) for identifier in result["products"]]
    assert nodes[0]["properties"]["attributes"]["mesh"] == 4
    assert nodes[1]["properties"]["attributes"]["mesh"] is None
    assert nodes[1]["properties"]["attributes"]["index_count"] == 2
    assert all(row["properties"]["attributes"]["space"] is None for row in nodes)
    assert all(
        row["properties"]["attributes"]["species_verified"] is None for row in nodes
    )
    assert all(row["properties"]["source_processing_activity"] is None for row in nodes)
    assert result["source_file_generation_claimed"] is False
    with store.connection() as db:
        generated = [
            dict(row)
            for row in db.execute("SELECT * FROM edges WHERE relation='wasGeneratedBy'")
        ]
        used = [
            dict(row) for row in db.execute("SELECT * FROM edges WHERE relation='used'")
        ]
    assert len(generated) == 1 and generated[0]["source"] == result["profile"]
    assert len(used) == 2
    assert store.integrity()["foreign_key_errors"] == []


def test_declarative_propagation_and_inactive_branch(tmp_path):
    store = database(tmp_path)
    workflows, _ = store.document("workflow_steps")
    steps = {step["id"]: step for step in workflows["steps"]}
    source = {"source": {"attributes": {"subject": "fixture", "hemisphere": "lh"}}}
    output = i.propagate(steps["freesurfer2caret"], 0, source, {})
    assert output["attributes"]["subject"] == "fixture"
    assert output["attributes"]["hemisphere"] == "lh"
    assert output["attributes"]["space"] == "fsLR_32k"
    assert output["attributes"]["mesh"] == 32492
    assert (
        i.propagate(steps["freesurfer2caret"], 0, source, {"low_res_mesh": 59}) is None
    )
    scaled = i.propagate(steps["rescale"], 0, source, {"scale_factor": 0.5})
    assert scaled["attributes"]["scale_status"]["factor"] == 0.5
    assert scaled["attributes"]["scale_status"]["verified"] is False


def test_six_unverified_facts_have_explicit_classification(tmp_path):
    definitions, _ = database(tmp_path).document("condition_templates")
    conditions = definitions["extra_method_conditions"]
    assert len(conditions) == 6
    assert sum(row["template"] == "advisory" for row in conditions) == 3
    assert {row["template"] for row in conditions} == {
        "advisory",
        "attr_in",
        "product_present",
    }
    assert all(row["source"] and row["classification_reason"] for row in conditions)


def test_sql_backed_planner_keeps_public_response_and_sources(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    planner = importlib.import_module(agent.__package__ + ".analysis_product_planner")
    result = planner.plan_analysis(
        tools, {"measures": ["thickness"], "regions": "aparc"}
    )
    candidates = result["candidates"]
    assert candidates and all(
        len(row["label_counts"]) == 2 and set(row["label_counts"].values()) == {2}
        for row in candidates
    )
    store = r.repository_for(tools)
    assert store.stats()["nodes_by_layer"]["instance"] > 0
    assert store.integrity()["foreign_key_errors"] == []
    assert tools.knowledge_metadata["unified_knowledge"]["knowledge_sha256"]


def test_unknown_template_refuses_execution():
    with pytest.raises(ValueError, match="Unknown condition template"):
        t.evaluate({"id": "bad", "template": "invented", "parameters": {}}, {})


def test_explicit_provenance_and_design_checks_can_pass():
    assert (
        t.provenance(
            {"slot": "x", "step": "rescale"},
            {
                "slots": {"x": [{"id": "a"}]},
                "provenance": {"a": [{"step": "rescale", "verified": True}]},
            },
        )["verdict"]
        == "pass"
    )
    assert (
        t.design_variable(
            {"slot": "x", "variable": "age"},
            {
                "slots": {
                    "x": [
                        {
                            "id": "a",
                            "attributes": {
                                "columns": ["age"],
                                "nonempty_columns": {"age": True},
                            },
                        }
                    ]
                }
            },
        )["verdict"]
        == "pass"
    )


def test_brainmask_is_skull_stripped_intensity_not_binary(tmp_path):
    store = database(tmp_path)
    actual = i.classify({"path": "/inputs/0/mri/brainmask.mgz", "format": "mgz"})
    assert store.is_subtype(actual, "type:Volume.T1")
    assert not store.is_subtype(actual, "type:Volume.BrainMask")
    assert (
        i.classify({"path": "/inputs/0/brain_mask.nii.gz", "format": "nifti"})
        == "type:Volume.BrainMask"
    )


def test_parallel_connections_and_transaction_rollback(tmp_path):
    import concurrent.futures

    store = database(tmp_path)

    def add(index):
        with store.transaction():
            store.node(
                "fixture:" + str(index),
                "instance",
                "Product",
                "fixture",
                {"index": index},
            )
            store.edge("fixture:" + str(index), "type:Volume", "instanceOf")

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(add, range(12)))
    assert len(store.find_nodes(layer="instance", kind="Product")) == 12
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.node("rolled-back", "instance", "Product", "bad", {})
            raise RuntimeError("synthetic rollback")
    assert store.get_node("rolled-back") is None
    assert store.integrity()["foreign_key_errors"] == []


def test_all_typed_workflow_inputs_have_attribute_contracts(tmp_path):
    store = database(tmp_path)
    workflows, _ = store.document("workflow_steps")
    assert len(workflows["steps"]) == 14
    for step in workflows["steps"]:
        assert step["source"] and step["input_attribute_contract_source"]
        for slot in step["inputs"]:
            assert slot["type"].startswith("type:")
            assert {"subject", "species", "scale_status"} <= slot["attributes"].keys()
            if slot["type"].startswith("type:Surface"):
                assert {"hemisphere", "mesh", "space"} <= slot["attributes"].keys()


def test_changed_release_cannot_leave_stale_active_edges(tmp_path):
    import shutil

    store = database(tmp_path)
    changed = tmp_path / "new-knowledge"
    shutil.copytree(ROOT, changed)
    path = changed / "workflow_steps.json"
    body = json.loads(path.read_bytes())
    body["scope"] = "synthetic new source version"
    path.write_text(json.dumps(body))
    path.with_suffix(".sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "\n"
    )
    before = store.stats()
    with pytest.raises(ValueError, match="select a new database"):
        store.import_knowledge(changed, None)
    assert store.stats() == before
    assert "scope" not in store.document("workflow_steps")[0]
