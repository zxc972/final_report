"""Phase control, strict output columns, receipts and model-view regressions."""

import copy
import csv
import importlib
import json
from pathlib import Path

import pytest

from test_analysis_agent import agent
from test_analysis_product_planner import p, setup_products

context = importlib.import_module(agent.__package__ + ".analysis_context")
operations = importlib.import_module(agent.__package__ + ".analysis_operations")


def sealed(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    result = tools.plan_analysis({"measures": ["thickness"], "regions": "all regions"})
    candidate = next(
        row for row in result["candidates"] if row["atlas"]["name"] == "aparc"
    )
    committed = tools._call(
        lambda: p.commit_candidate(
            tools,
            candidate["candidate_id"],
            "Synthetic engineering fixture",
            "/work/analysis.py",
        )
    )
    assert committed["status"] == "committed"
    return tools, candidate, committed


def fake_execution(tools):
    class Executor:
        def run(self, script, **kwargs):
            bundle = tools.control_store.latest("execution_bundle")["record"]
            columns = list(bundle["output_contract"]["csv_columns"])
            if "missing_column" in script.read_text():
                columns.remove("metric")
            with (tools.workdir / "summary.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                # Satisfy the public identity contract; values remain a synthetic
                # engineering fixture, not private numerical reference answers.
                for identity in bundle["output_contract"]["table"]["expected_identities"]:
                    row = {**identity, "vertex_count": 3, "mean": 1.234567891234,
                           "std_population": 0.234567891234, "median": 1.234567891234,
                           "zero_count": 0, "units": "synthetic stored units"}
                    writer.writerow({key: row[key] for key in columns})
            (tools.workdir / "summary.json").write_text(
                json.dumps(
                    {
                        "methods": "Synthetic fixture",
                        "limitations": "No scientific claim",
                    }
                )
            )
            (tools.workdir / "report.md").write_text(
                "Engineering fixture; physical scale unverified."
            )
            return {
                "status": "success",
                "exit_code": 0,
                "stdout": "fixture",
                "stderr": "",
            }

    tools.executor = Executor()


def test_wrong_path_refused_then_default_path_auto_finalizes(tmp_path, monkeypatch):
    tools, candidate, committed = sealed(tmp_path, monkeypatch)
    fake_execution(tools)
    assert committed["state"]["phase"] == "sealed"
    wrong = tools.write_code("/work/wrong.py", "print('wrong')")
    assert wrong["status"] == "error"
    assert "Edit /work/analysis.py instead" in wrong["error"]
    assert not (tools.workdir / "wrong.py").exists()
    assert (
        tools.write_code("/work/analysis.py", "print('fixture')")["status"] == "written"
    )
    executed = tools.run_python()
    assert executed["exit_code"] == 0
    assert executed["state"]["phase"] == "finalized", executed
    assert executed["automatic_finalization"]["status"] == "finalized"
    assert len(context.serialized(executed["state"])) <= 400
    receipt = tools.finalize_artifacts([{"path": "summary.csv", "kind": "csv"}])
    assert receipt["already_finalized"]
    assert (
        receipt["artifact_receipt_id"]
        == executed["automatic_finalization"]["artifact_receipt_id"]
    )
    assert tools.tool_calls == 6
    assert tools.executions == 1
    assert tools.session.record["wrong_path_blocks"] == 1
    phases = [
        tools.control_store.read(path.name)["record"]["phase"]
        for path in tools.control_store.versions("session")
    ]
    assert "executed_ok" in phases and phases[-1] == "finalized"


def test_reseal_same_candidate_new_path_keeps_history(tmp_path, monkeypatch):
    tools, candidate, first = sealed(tmp_path, monkeypatch)
    second = tools._call(
        lambda: p.commit_candidate(
            tools,
            candidate["candidate_id"],
            "Use another explicit script filename",
            "/work/revised.py",
        )
    )
    assert second["status"] == "committed"
    assert second["version"] == first["version"] + 1
    assert second["state"]["code_path"] == "/work/revised.py"
    assert len(tools.control_store.versions("plan")) == 2
    assert tools.write_code("/work/analysis.py", "print(1)")["status"] == "error"
    assert tools.write_code("/work/revised.py", "print(2)")["status"] == "written"


def test_missing_column_is_actionable_and_manual_finalize_cannot_bypass(
    tmp_path, monkeypatch
):
    tools, _, _ = sealed(tmp_path, monkeypatch)
    fake_execution(tools)
    tools.write_code("/work/analysis.py", "# missing_column\nprint('fixture')")
    first = tools.run_python()
    assert first["exit_code"] == 0
    assert first["state"]["phase"] == "executed_failed"
    assert "summary.csv: missing column metric" in context.serialized(first["state"])
    bypass = tools.finalize_artifacts([{"path": "summary.csv", "kind": "csv"}])
    assert bypass["status"] == "error" and "missing column metric" in bypass["error"]
    tools.write_code("/work/analysis.py", "print('corrected fixture')")
    second = tools.run_python()
    assert second["state"]["phase"] == "finalized", second
    assert tools.executions == 2
    assert (
        len(
            list(
                (
                    tools.workdir.parent / ".execution_receipts" / tools.workdir.name
                ).glob("*.json")
            )
        )
        == 2
    )


def test_changed_finalized_output_cannot_reuse_receipt(tmp_path, monkeypatch):
    tools, _, _ = sealed(tmp_path, monkeypatch)
    fake_execution(tools)
    tools.write_code("/work/analysis.py", "print('fixture')")
    assert tools.run_python()["state"]["phase"] == "finalized"
    (tools.workdir / "report.md").write_text("Changed after finalization.")
    result = tools.finalize_artifacts([{"path": "summary.csv", "kind": "csv"}])
    assert result["status"] == "error"
    assert "Finalized outputs changed" in result["error"]


def test_actual_operation_examples_cover_all_functions():
    catalogue = operations.operations_manifest()
    assert len(catalogue["functions"]) == 12  # Round15 adds two low-level readers.
    assert {"read_stats_measures", "positive_mask_volume"} <= {r["name"] for r in catalogue["functions"]}
    for row in catalogue["functions"]:
        assert "returns_example" in row
        assert row["example_scope"].startswith("Actual synthetic")
    summary = next(
        row["returns_example"]
        for row in catalogue["functions"]
        if row["name"] == "parcel_summary"
    )
    assert set(summary[0]) == {
        "label_key",
        "name",
        "vertex_count",
        "mean",
        "std_population",
        "median",
        "zero_count",
        "weight_sum",
    }
    assert "key" not in summary[0]


def test_bounded_returns_and_complete_recoverable_file(tmp_path, monkeypatch):
    tools, _, committed = sealed(tmp_path, monkeypatch)
    original = copy.deepcopy(committed)
    result = tools.model_context.offload("commit_plan", committed)
    assert len(context.serialized(result)) <= 4000
    assert len(result["execution_card"]) <= 1500
    assert "Code: /work/analysis.py" in result["execution_card"]
    assert "Labels: /work/label_sets." in result["execution_card"]
    bundle_ref = original["execution_bundle"]["bundle_ref"]
    recovered = json.loads(tools.resolve(bundle_ref).read_text())
    assert recovered == {key: val for key, val in original["execution_bundle"].items() if key != "label_sets"}
    assert tools.control_store.latest("plan")["sha256"] == original["plan_sha256"]
    assert committed == original


def test_source_compaction_keeps_latest_code_and_protocol_ids():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "one",
                    "function": {
                        "name": "write_code",
                        "arguments": json.dumps(
                            {"path": "/work/a.py", "code": "x=1\n" * 3000}
                        ),
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "one", "content": '{"status":"written"}'},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "two",
                    "function": {
                        "name": "write_code",
                        "arguments": json.dumps(
                            {"path": "/work/a.py", "code": "x=2\n"}
                        ),
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "two", "content": '{"status":"written"}'},
    ]
    old = copy.deepcopy(messages)
    result = context.compact_messages(messages)
    assert messages == old
    assert "Superseded" in result[0]["tool_calls"][0]["function"]["arguments"]
    assert result[2] == old[2]
    assert result[1]["tool_call_id"] == "one" and result[3]["tool_call_id"] == "two"


def test_legacy_has_no_session_or_context_rewrite(tmp_path, monkeypatch):
    from test_analysis_knowledge_profiles import make_tools

    tools = make_tools(tmp_path, monkeypatch, "legacy_v13")
    assert tools.session is None and tools.model_context is None
    result = tools.write_code("/work/first.py", "print('fixture')")
    assert result["status"] == "written"
    assert "state" not in result
    assert (
        tools.write_code("/work/another.py", "print('fixture')")["status"] == "written"
    )

