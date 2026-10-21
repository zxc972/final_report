"""Offline Round 7 boundary, commitment and post-commit observation tests."""

import importlib, json
from types import SimpleNamespace
from test_analysis_agent import agent
from test_analysis_product_planner import setup_products, p
from test_analysis_knowledge_profiles import make_tools, capture_builder
from langchain_core.messages import ToolMessage

ops = importlib.import_module(agent.__package__ + ".analysis_operations")
lobes = importlib.import_module(agent.__package__ + ".analysis_lobar_mapping")


def test_operations_candidates_and_complete_commit_bundle(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    result = p.plan_analysis(
        tools, {"measures": ["thickness"], "regions": "all regions"}
    )
    candidate = result["candidates"][0]
    calls = candidate["operations"]["calls"]
    assert {
        "read_annotation",
        "read_surface_metric",
        "read_label",
        "parcel_summary",
    } <= {x["function"] for x in calls}
    committed = p.commit_candidate(
        tools,
        candidate["candidate_id"],
        "Summarise supplied cortex with explicit exclusions.",
        "/work/analysis.py",
    )
    assert committed["status"] == "committed"
    bundle = committed["execution_bundle"]
    assert bundle["output_contract"]["csv_columns"] and bundle["input_paths"]
    assert tools.resolve(bundle["label_sets_ref"]["path"]).is_file()
    assert (
        tools.control_store.latest("execution_bundle")["record"]["plan_sha256"]
        == committed["plan_sha256"]
    )


def test_post_seal_browsing_warns_but_executes(tmp_path, monkeypatch):
    tools = setup_products(tmp_path, monkeypatch)
    c = p.plan_analysis(tools, {"measures": ["thickness"]})["candidates"][0]
    p.commit_candidate(
        tools,
        c["candidate_id"],
        "Use the observed native products.",
        "/work/analysis.py",
    )
    out = tools.events.call_tool(
        "ls",
        {"path": "/inputs/0"},
        lambda: ToolMessage(
            content='{"status":"ok","files":[]}', tool_call_id="fixture"
        ),
        tool_call_id="fixture",
    )
    payload = json.loads(out.content)
    assert (
        payload["status"] == "ok"
        and payload["post_commit_retrieval_or_browse_count"] == 1
    )
    assert (
        payload["plan_sealed_notice"]
        == "Plan sealed: write and run the analysis script next"
    )
    assert tools.events.all()[-1]["status"] == "warn"
    assert tools.events.plan_summary()["constraints"]["unverified"] >= 0


def test_legacy_exposure_and_prompt_still_exact(tmp_path, monkeypatch):
    tools = make_tools(tmp_path, monkeypatch, "legacy_v13")
    captured = capture_builder(tools, monkeypatch)
    assert "read_operations" not in [x.name for x in captured["tools"]]
    import hashlib

    assert len(captured["system_prompt"].encode()) == 7652
    assert (
        hashlib.sha256(captured["system_prompt"].encode()).hexdigest()
        == "de5e8d8832491221c1f85793ca213c6b27f27dc0c193ad2d74cd9daa607bcecc"
    )
    assert tools.operations_metadata is None


def test_human_frontal_official_and_monkey_not_transferred():
    mapping, _ = p.load_knowledge("lobar_mapping")
    names = list(
        {n for row in mapping["records"] if row["atlas"] == "DK" for n in row["labels"]}
    )
    selected, source, error = lobes.resolve_lobes(
        {"species_declared": "human"}, "aparc", "frontal lobe", names
    )
    assert not error and "precentral" in selected and "paracentral" in selected
    assert (
        len(selected) == 11
        and "postcentral" not in selected
        and source[0]["source_url"].startswith("https://surfer.")
    )
    _, _, error = lobes.resolve_lobes(
        {"species_declared": "monkey_unknown"}, "aparc", "frontal lobe", names
    )
    assert "CHARM" in error and "human-named aparc" in error


def test_dkt_protocol_adaptation_and_missing_label_fail():
    mapping, _ = p.load_knowledge("lobar_mapping")
    names = list(
        {
            n
            for row in mapping["records"]
            if row["atlas"] == "DKT"
            for n in row["labels"]
        }
    )
    selected, _, error = lobes.resolve_lobes(
        {"species_declared": "human"}, "aparc.DKTatlas", "frontal lobe", names
    )
    assert not error and len(selected) == 10 and "frontalpole" not in selected
    _, _, error = lobes.resolve_lobes(
        {"species_declared": "human"}, "aparc", "frontal lobe", ["precentral"]
    )
    assert "missing" in error


def test_operation_mount_is_read_only_hashed_and_optional(tmp_path):
    executor_module = importlib.import_module(agent.__package__ + ".analysis_executor")
    work = tmp_path / "work"
    data = tmp_path / "data"
    data.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    image = tmp_path / "image.sif"
    image.write_text("synthetic")
    executor = executor_module.SandboxExecutor(
        work, [data], runtime_env=runtime, runtime_image=image, fs_license_file=None
    )
    before = executor._command(work, [data], ["/work/probe.py"])
    assert "/opt/primatex_ops.py" not in " ".join(before)
    manifest = ops.operations_manifest()
    executor.enable_operations(ops.SOURCE, manifest["sha256"])
    after = executor._command(work, [data], ["/work/probe.py"])
    assert str(ops.SOURCE) + ":/opt/primatex_ops.py:ro" in after
    assert "-I" in after and any(manifest["sha256"] in word for word in after)
    bad = tmp_path / "bad.py"
    bad.write_text("pass")
    import pytest

    with pytest.raises(ValueError):
        executor.enable_operations(bad, "0" * 64)
