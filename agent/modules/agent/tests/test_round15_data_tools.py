"""Safety and provenance checks for explicit PRIME-DE structural selection."""

import csv
import importlib.util
import io
from pathlib import Path
import tarfile

import pytest

TOOL = Path(__file__).resolve().parents[4] / "tools" / "prepare_prime_structural.py"
spec = importlib.util.spec_from_file_location("prime_structural", TOOL)
prime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prime)


def participants(path):
    path.write_text(
        "Subject ID,Species,Age (Years),Sex\n32198,Macaca mulatta,5.81,Male\n32200,Macaca fascicularis,5.38,Female\n",
        encoding="utf-8",
    )
    return path


def archive(path, entries):
    with tarfile.open(path, "w:gz") as stream:
        for name, content in entries:
            member = tarfile.TarInfo(name)
            member.size = len(content)
            stream.addfile(member, io.BytesIO(content))
    return path


def test_individual_species_record_and_held_out_are_required(tmp_path):
    source = participants(tmp_path / "participants.csv")
    assert (
        prime.select_participants(source, ["32198"])[0]["Species"] == "Macaca mulatta"
    )
    with pytest.raises(ValueError, match="Macaca mulatta"):
        prime.select_participants(source, ["32200"])
    with pytest.raises(ValueError, match="Held-out"):
        prime.select_participants(source, ["32198"], ["32198"])
    with pytest.raises(ValueError, match="distinct"):
        prime.select_participants(source, ["32198", "32198"])


def test_only_selected_anatomical_files_and_no_overwrite(tmp_path):
    name = "site-ion/sub-032198/ses-001/anat/sub-032198_T1w.json"
    source = archive(
        tmp_path / "data.tar.gz",
        [
            (name, b"{}"),
            ("site-ion/sub-032200/anat/other.json", b"{}"),
            ("site-ion/sub-032198/func/bold.nii.gz", b"ignored"),
        ],
    )
    output = tmp_path / "raw"
    records = prime.extract_structural(source, output, ["32198"])
    assert len(records) == 1
    assert records[0]["raw_sha256"] == prime.sha256(output / name)
    assert prime.extract_structural(source, output, ["32198"]) == records
    assert not (output / "site-ion/sub-032200").exists()
    (output / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="refusing overwrite"):
        prime.extract_structural(source, output, ["32198"])
    assert (output / name).read_bytes() == b"changed"


def test_selected_archive_traversal_is_rejected(tmp_path):
    source = archive(tmp_path / "bad.tar.gz", [("../sub-032198/anat/x.json", b"{}")])
    with pytest.raises(ValueError, match="Unsafe"):
        prime.extract_structural(source, tmp_path / "raw", ["32198"])
    assert not (tmp_path / "sub-032198").exists()


def test_unknown_header_units_are_not_claimed_as_mm(tmp_path):
    nib = pytest.importorskip("nibabel")
    np = pytest.importorskip("numpy")
    path = tmp_path / "t1.nii.gz"
    nib.save(
        nib.Nifti1Image(
            np.zeros((2, 3, 4), dtype=np.float32), np.diag([0.5, 0.5, 0.5, 1])
        ),
        path,
    )
    record = prime.header_record(path)
    assert record["voxel_size_stored"] == [0.5, 0.5, 0.5]
    assert record["voxel_size_unit"] == "unknown"
    assert record["voxel_size_mm"] is None
    assert record["source"]["path"] == str(path)


def test_repeat_structural_sessions_do_not_increase_subject_n(tmp_path):
    nib = pytest.importorskip("nibabel")
    np = pytest.importorskip("numpy")
    source = participants(tmp_path / "participants.csv")
    files = []
    for session in ("001", "002"):
        path = tmp_path / ("ses-" + session) / "sub-032198_T1w.nii.gz"
        path.parent.mkdir()
        image = nib.Nifti1Image(np.zeros((2, 3, 4), dtype=np.float32), np.eye(4))
        image.header.set_xyzt_units("mm")
        nib.save(image, path)
        files.append(
            {"subject_id": "32198", "path": str(path), "raw_sha256": prime.sha256(path)}
        )
    rows = prime.build_manifest(
        "ion",
        source,
        prime.select_participants(source, ["32198"]),
        files,
        "official-site",
        "official-download",
    )
    assert len(rows) == 1
    assert len(rows[0]["t1_files"]) == 2
    assert "ses-001" in rows[0]["t1_file"]
    assert rows[0]["header"]["voxel_size_mm"] == [1.0, 1.0, 1.0]
    assert rows[0]["species_verified"] == "declared_by_individual_dataset_record"
    assert rows[0]["scale_status"] == "unknown"
