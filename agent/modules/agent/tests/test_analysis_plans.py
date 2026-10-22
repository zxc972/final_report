"""Offline plan sealing, immutable versions and real tool gate decisions."""

import importlib
import json
from pathlib import Path

import pytest

from test_analysis_agent import agent
from test_analysis_knowledge_profiles import make_tools, capture_builder
from test_analysis_constraints import file, profile, context, f, c

plans = importlib.import_module(agent.__package__ + ".analysis_plans")


def ready(tmp_path, monkeypatch, name="method_graph_gated"):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, name)
    monkeypatch.setattr(
        c,
        "software_observation",
        lambda tools, commands, method_id: (
            True,
            {"commands": [{"command": command, "executable": True, "exit_code": 0} for command in commands],
             "scope": "synthetic availability observations for plan tests"},
        ),
    )
    observed = tools.input_roots[0] / "lh.pial"
    observed.write_text("synthetic input fingerprint", encoding="utf-8")
    row = file()
    worker = importlib.import_module(agent.__package__ + ".analysis_profile_worker")
    row["sha256"] = f(worker.file_hash(observed)[0])
    saved = tools.control_store.save("data_profile", profile([row]))
    plan = context([row["path"]["value"]])
    plan["data"]["profile_sha256"] = saved["sha256"]
    result = tools.compile_constraints("self:synthetic", "geometry", plan)
    assert result["status"] == "ok"
    plan["constraints"] = {
        "version": result["version"],
        "sha256": result["constraints_sha256"],
    }
    return tools, plan


def test_seal_version_and_warning_disclosures(tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch)
    first = tools.commit_plan(plan)
    assert first["status"] == "committed" and first["version"] == 1
    assert (
        first["must_disclose"][0]["constraint_id"] == "scale_consistent:physical_scale"
    )
    second = tools.commit_plan(
        {
            **plan,
            "revision_reason": "Explain retained scope after reviewing null physical calibration",
        }
    )
    assert second["status"] == "committed" and second["version"] == 2
    assert plans.plan_history(tools.control_store)[0]["version"] == 1
    assert (
        tools.control_store.read("plan.v000001.json")["sha256"] == first["plan_sha256"]
    )


def test_hard_block_rejected_even_if_work_copy_is_forged(tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch)
    old = tools.control_store.latest("constraints")["record"]
    row = {
        "constraint_id": "software_available",
        "severity": "hard",
        "verdict": "block",
        "tool_observed": {"missing": "MATLAB"},
    }
    old["rows"].append(row)
    saved = tools.control_store.save("constraints", old)
    plan["constraints"] = {"version": saved["version"], "sha256": saved["sha256"]}
    (tools.workdir / "constraints.json").write_text('{"rows":[]}', encoding="utf-8")
    result = tools.commit_plan(plan)
    assert result["status"] == "blocked"
    assert result["blocked_constraints"][0]["constraint_id"] == "software_available"
    assert result["next_steps"] and not tools.control_store.versions("plan")


@pytest.mark.parametrize(
    "field",
    ["question", "data", "atlas", "method", "constraints", "outputs", "code_path"],
)
def test_missing_required_plan_fields_rejected(field, tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch)
    del plan[field]
    assert tools.commit_plan(plan)["status"] == "error"


def test_plan_change_requires_recompile_and_revision_reason(tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch)
    assert tools.commit_plan(plan)["status"] == "committed"
    plan["question"] = "Changed synthetic question"
    assert tools.commit_plan(plan)["status"] == "blocked"
    checked = tools.compile_constraints("self:synthetic", "geometry", plan)
    plan["constraints"] = {
        "version": checked["version"],
        "sha256": checked["constraints_sha256"],
    }
    assert tools.commit_plan(plan)["status"] == "error"
    plan["revision_reason"] = "Question clarified; recompiled same data scope"
    assert tools.commit_plan(plan)["version"] == 2


def test_gated_production_needs_commit_and_matching_script(tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch)
    tools.write_code(
        "/work/analysis.py",
        "from pathlib import Path\nPath('summary.json').write_text('{}')\n",
    )
    calls = []
    tools.executor.run = lambda *args, **kwargs: calls.append((args, kwargs)) or {
        "status": "success",
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
    }
    blocked = tools.run_python("/work/analysis.py")
    assert blocked["status"] == "blocked" and not calls and tools.executions == 0
    assert tools.commit_plan(plan)["status"] == "committed"
    passed = tools.run_python("/work/analysis.py")
    assert passed["status"] == "success" and len(calls) == 1
    assert passed["plan_gate"]["plan_version"] == 1
    tools.write_code("/work/other.py", "open('out','w').write('x')")
    assert tools.run_python("/work/other.py")["status"] == "blocked"
    assert len(calls) == 1


def test_read_only_inspection_uses_ro_mount_and_cannot_finalize(tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch)
    tools.write_code(
        "/work/inspect.py",
        "from pathlib import Path\nprint(Path('/inputs/0').is_dir())\n",
    )
    calls = []
    tools.executor.run = lambda *args, **kwargs: calls.append(kwargs) or {
        "status": "success",
        "exit_code": 0,
        "stdout": "True",
        "stderr": "",
    }
    result = tools.run_python("/work/inspect.py")
    assert result["status"] == "inspected" and calls == [
        {"timeout_seconds": 120, "work_read_only": True}
    ]
    assert tools.finalize_artifacts([])["status"] == "error"


@pytest.mark.parametrize(
    "source",
    [
        "open('out','w').write('x')",
        "import subprocess\nsubprocess.run(['true'])",
        "from pathlib import Path\nPath('/work/out').write_text('x')",
        "import os\nos.system('true')",
        "exec('print(1)')",
        "from pathlib import Path\nprint(Path('/etc/passwd').read_text())",
        "from pathlib import Path\np=Path('/inputs/0'); print(p.__class__)",
        "import nibabel as nib\nimage=nib.load('/inputs/0/t1.nii');nib.save(image,'/work/out.nii')",
    ],
)
def test_unknown_or_writing_scripts_never_self_declare_read_only(
    source, tmp_path, monkeypatch
):
    tools, plan = ready(tmp_path, monkeypatch)
    assert plans.read_only_inspection(source, tools.resolve) is False


def test_background_cannot_bypass_gate(tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch)
    tools.write_code("/work/analysis.py", "open('out','w').write('x')")
    result = tools.submit_python_job("/work/analysis.py", [])
    assert result["status"] == "blocked"
    assert not tools.analysis_jobs


def test_non_gated_method_profile_keeps_execution_optional_plan(tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch, "method_graph")
    tools.write_code("/work/plain.py", "print('synthetic')")
    assert tools.run_python("/work/plain.py")["status"] == "success"


def test_executor_readonly_mount_is_actual_command_setting(tmp_path):
    from test_analysis_executor import SandboxExecutor

    runtime = tmp_path / "runtime"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin/python").write_text("fixture")
    data = tmp_path / "data"
    data.mkdir()
    image = tmp_path / "image.sif"
    image.write_text("fixture")
    executor = SandboxExecutor(
        tmp_path / "work",
        [data],
        runtime_image=image,
        runtime_env=runtime,
        fs_license_file=None,
    )
    command = executor._command(
        executor.workdir, [data], ["-c", "print('header')"], work_read_only=True
    )
    assert str(executor.workdir) + ":/work:ro" in command
    assert str(data) + ":/inputs/0:ro" in command


def test_changed_input_fingerprint_invalidates_commit(tmp_path, monkeypatch):
    tools, plan = ready(tmp_path, monkeypatch)
    assert tools.commit_plan(plan)["status"] == "committed"
    tools.write_code("/work/analysis.py", "open('summary.json', 'w').write('{}')")
    (tools.input_roots[0] / "lh.pial").write_text("changed input", encoding="utf-8")
    result = tools.run_python("/work/analysis.py")
    assert result["status"] == "blocked" and tools.executions == 0
    assert "fingerprint" in result["reason"]


def test_graph_reports_prerequisite_block_without_repeated_coding_turns(
    tmp_path, monkeypatch
):
    from langgraph.checkpoint.memory import InMemorySaver

    tools, plan = ready(tmp_path, monkeypatch)
    monkeypatch.setattr(
        c,
        "software_observation",
        lambda *args: (
            False,
            {"commands": [{"command": "matlab", "executable": False}]},
        ),
    )

    class ScriptedCoder:
        calls = 0

        def invoke(self, payload, config):
            self.calls += 1
            tools.compile_constraints("self:synthetic", "geometry", plan)
            return {
                "messages": [
                    {
                        "content": "Synthetic prerequisite missing; no production execution."
                    }
                ]
            }

    class MustNotValidateMissingArtifacts:
        def validate(self, workdir):
            raise AssertionError(
                "Prerequisite-blocked tasks must not claim artifact evaluation"
            )

    coder = ScriptedCoder()
    graph = agent._build_graph(
        coder, tools, MustNotValidateMissingArtifacts(), InMemorySaver()
    )
    result = graph.invoke(
        {
            "request": "Synthetic prerequisite block",
            "history": [],
            "required_artifacts": [],
            "iterations": 0,
            "feedback": "",
        },
        {"configurable": {"thread_id": "fixture-block"}},
    )
    assert result["status"] == "blocked"
    assert result["validation"]["scope"] == "method_constraint_block"
    assert result["validation"]["scientific_status"] == "not_evaluated"
    assert coder.calls == 1 and tools.executions == 0
    # The scripted model omitted warnings; the deterministic report must still
    # disclose the tool-observed unverified physical scale.
    assert "物理尺度未独立核实" in result["message"]
