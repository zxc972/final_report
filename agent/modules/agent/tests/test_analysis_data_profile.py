"""Synthetic header/annotation fixtures; no participant imaging or API calls."""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_analysis_agent import agent, FakeKnowledge, TestOnlyExecutor
from test_analysis_knowledge_profiles import make_tools, capture_builder

worker = importlib.import_module(agent.__package__ + ".analysis_profile_worker")
store_module = importlib.import_module(agent.__package__ + ".analysis_control_store")


def test_missing_file_is_null_not_invented(tmp_path):
    result = worker.build_profile([str(tmp_path / "monkey_missing.nii.gz")])
    row = result["files"][0]
    assert row["volume"]["value"] is None
    assert row["sha256"]["value"] is None
    assert row["read_error"]["reason"]
    assert result["species"]["verified"]["value"] is None
    assert result["species"]["declared"]["value"] is None


def test_table_subjects_deduplicate_scans_and_sources(tmp_path):
    path = tmp_path / "participants.tsv"
    path.write_text(
        "participant_id\tsession_id\nsub-one\ta\nsub-one\tb\n", encoding="utf-8"
    )
    result = worker.profile_file(path)
    assert result["subject"]["value"] == ["sub-one"]
    assert result["sha256"]["source"]["method"] == "sha256_full_file"
    for entry in result.values():
        assert "source" in entry


def test_recon_counts_lines_without_interpreting_severity(tmp_path):
    base = tmp_path / "subject"
    (base / "stats").mkdir(parents=True)
    (base / "scripts").mkdir()
    path = base / "stats/lh.aparc.stats"
    path.write_text("# synthetic fixture", encoding="utf-8")
    (base / "scripts/recon-all.done").touch()
    (base / "scripts/recon-all.log").write_text(
        "start\nFATAL test\nERROR test\n", encoding="utf-8"
    )
    recon = worker.profile_file(path)["recon"]["value"]
    assert recon["done"]["value"] is True
    assert recon["fatal_count"]["value"] == 1
    assert recon["fatal_lines"]["value"] == [2]
    assert recon["error_lines"]["value"] == [3]


def test_control_store_rejects_mount_overlap_and_versions(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(ValueError, match="overlaps"):
        store_module.ControlStore(work / "private", [work])
    state = store_module.ControlStore(tmp_path / "protected", [work])
    first = state.save("data_profile", {"observed": True})
    second = state.save("data_profile", {"observed": False})
    assert (first["version"], second["version"]) == (1, 2)
    assert state.latest("data_profile") == second
    with pytest.raises(FileExistsError):
        state.create("data_profile.v000001.json", {})


@pytest.mark.parametrize(
    "name", ["legacy_v13", "no_knowledge", "text_retrieval", "text_plus_rules"]
)
def test_original_groups_have_no_control_state_or_new_tools(
    name, tmp_path, monkeypatch
):
    tools = make_tools(tmp_path, monkeypatch, name)
    captured = capture_builder(tools, monkeypatch)
    assert tools.control_store is None
    assert not {"profile_data", "compile_constraints", "commit_plan"} & {
        t.name for t in captured["tools"]
    }


@pytest.mark.parametrize("name", ["method_graph", "method_graph_gated"])
def test_method_groups_profile_tool_and_protected_state(name, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, name)
    captured = capture_builder(tools, monkeypatch)
    assert "profile_data" in {tool.name for tool in captured["tools"]}
    assert not tools.control_store.root.is_relative_to(tools.workdir)


def test_model_cannot_profile_unapproved_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, "method_graph")
    assert tools.profile_data(["/etc/passwd"])["status"] == "error"
    assert not (tools.workdir / "data_profile.json").exists()


def test_explicit_species_only():
    profiler = importlib.import_module(agent.__package__ + ".analysis_data_profile")
    assert (
        profiler.explicit_species("species=monkey_unknown; inspect headers")
        == "monkey_unknown"
    )
    assert profiler.explicit_species("inspect macaque_T1.nii.gz") is None


@pytest.fixture
def scientific_modules():
    np = pytest.importorskip("numpy")
    nib = pytest.importorskip("nibabel")
    return np, nib


def test_synthetic_nifti_qform_sform_conflict_and_unknown_units(
    tmp_path, scientific_modules
):
    np, nib = scientific_modules
    path = tmp_path / "monkey_filename_is_not_species.nii.gz"
    image = nib.Nifti1Image(np.zeros((3, 4, 5), dtype=np.int16), np.eye(4))
    image.set_qform(np.eye(4), code=1)
    shift = np.eye(4)
    shift[0, 3] = 10
    image.set_sform(shift, code=2)
    nib.save(image, str(path))
    result = worker.build_profile([str(path)])
    header = result["files"][0]["volume"]["value"]
    assert header["shape"]["value"] == [3, 4, 5]
    assert header["voxel_size_mm"]["value"] is None
    assert header["qform_sform_conflict"]["value"] is True
    assert result["species"]["verified"]["value"] is None


def test_synthetic_surface_and_annot_minus_one_cardinality(
    tmp_path, scientific_modules
):
    np, nib = scientific_modules
    root = tmp_path / "subject"
    (root / "surf").mkdir(parents=True)
    (root / "label").mkdir()
    surface = root / "surf/lh.pial"
    annotation = root / "label/lh.aparc.annot"
    nib.freesurfer.write_geometry(
        str(surface),
        np.array([[0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0]]),
        np.array([[0, 1, 2]]),
    )
    ctab = np.array([[1, 2, 3, 0], [4, 5, 6, 0]], dtype=np.int32)
    nib.freesurfer.write_annot(
        str(annotation),
        np.array([-1, 0, 1], dtype=np.int32),
        ctab,
        [b"unknown", b"region"],
    )
    result = worker.build_profile([str(surface), str(annotation)])
    label = result["files"][1]["label"]["value"]
    assert label["unassigned_vertices"]["value"] == 1
    assert label["special_vertices"]["value"]["unknown"] == 1
    assert label["surface_vertex_match"]["value"][0]["equal"] is True
    assert result["files"][0]["surface"]["value"]["face_count"]["value"] == 1


def test_synthetic_gifti_nonordinal_unknown_label_key(tmp_path, scientific_modules):
    np, nib = scientific_modules
    path = tmp_path / "lh.regions.label.gii"
    image = nib.gifti.GiftiImage(
        darrays=[
            nib.gifti.GiftiDataArray(
                np.array([-1, 42, 7], dtype=np.int32), intent="NIFTI_INTENT_LABEL"
            )
        ]
    )
    for key, name in [(42, "unknown"), (7, "region")]:
        label = nib.gifti.GiftiLabel(key=key)
        label.label = name
        image.labeltable.labels.append(label)
    nib.save(image, str(path))
    label = worker.profile_file(path)["label"]["value"]
    assert label["special_vertices"]["value"]["unknown"] == 1
    assert label["unassigned_vertices"]["value"] == 1


def test_surface_format_uses_magic_when_mount_hides_surf_directory_name(tmp_path):
    path = tmp_path / "lh.pial"
    path.write_bytes(bytes.fromhex("fffffe") + b"synthetic header")
    assert worker.file_format(path) == "surface"
    morph = tmp_path / "lh.curv"
    morph.write_bytes(bytes.fromhex("ffffff") + b"synthetic morphometry header")
    # FreeSurfer curv and legacy quad have the same first magic. A named curv
    # overlay must never be treated as triangle geometry just from its prefix.
    assert worker.file_format(morph) == "surface_metric"


def test_complete_frozen_profile_program_executes_with_frozen_arguments(
    tmp_path, monkeypatch
):
    import subprocess
    import sys

    monkeypatch.setenv("AGENT_ANALYSIS_STATE_DIR", str(tmp_path / "state"))
    tools = make_tools(tmp_path, monkeypatch, "method_graph")
    table = tools.input_roots[0] / "participants.tsv"
    table.write_text("participant_id\nsynth-one\n", encoding="utf-8")
    tools.task_request = "Inspect fixture; species=human; metadata only"

    def execute_fixture(script, timeout_seconds=120, frozen_source=None):
        assert frozen_source and not frozen_source.is_relative_to(tools.workdir)
        source = frozen_source.read_text(encoding="utf-8")
        assert ".profile_request.json" not in source
        # Test-only filesystem adapter. Execute the WHOLE immutable probe, with
        # only container mount prefixes translated to temporary fixture roots.
        source = source.replace("/inputs/0", tools.input_roots[0].as_posix())
        source = source.replace(
            "/work/data_profile.json", (tools.workdir / "data_profile.json").as_posix()
        )
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", source],
            cwd=tools.workdir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if result.returncode == 0:
            path = tools.workdir / "data_profile.json"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    tools.input_roots[0].as_posix(), "/inputs/0"
                ),
                encoding="utf-8",
            )
        return {
            "status": "success" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "backend": "synthetic-mount-prefix-adapter-not-real-container",
        }

    tools.executor.run = execute_fixture
    first = tools.profile_data(["/inputs/0/participants.tsv"])
    assert first["status"] == "ok", first
    assert first["profile"]["species"]["declared"]["value"] == "human"
    assert first["profile"]["files"][0]["subject"]["value"] == ["synth-one"]
    assert len(first["profile"]["request_id"]) == 32
    assert not (tools.workdir / ".profile_request.json").exists()
    # A stale output from the preceding successful probe must not be accepted.
    tools.executor.run = lambda *args, **kwargs: {"status": "success", "exit_code": 0}
    stale = tools.profile_data(["/inputs/0/participants.tsv"])
    assert stale["status"] == "error" and "Unexpected profile" in stale["error"]
    assert tools.control_store.latest("data_profile")["version"] == 1


def test_synthetic_mgz_profile_serializes_header_dimensions(tmp_path, scientific_modules):
    np, nib = scientific_modules
    path = tmp_path / "orig.mgz"
    nib.save(nib.MGHImage(np.zeros((3, 4, 5), dtype=np.int16), np.eye(4)), str(path))
    result = worker.build_profile([str(path)])
    dimensions = result["files"][0]["volume"]["value"]["shape"]["value"]
    assert dimensions == [3, 4, 5]
    assert all(type(size) is int for size in dimensions)
    # Strict production JSON must accept the complete profile, not just a field.
    serialized = json.dumps(result, allow_nan=False)
    assert json.loads(serialized)["files"][0]["volume"]["value"]["shape"]["value"] == [3, 4, 5]

def test_synthetic_morphometry_is_profiled_with_counts_and_null_units(tmp_path):
    np = pytest.importorskip('numpy')
    nib = pytest.importorskip('nibabel')
    path = tmp_path / 'lh.thickness'
    nib.freesurfer.write_morph_data(str(path), np.asarray([1.0, 2.0, 3.0], dtype=np.float32))
    row = worker.profile_file(path)
    assert worker.value(row['format']) == 'surface_metric'
    detail = worker.value(row['metric'])
    assert worker.value(detail['vertex_count']) == 3
    assert worker.value(detail['finite_count']) == 3
    assert worker.value(detail['units']) is None
    assert 'source' in detail['units']
