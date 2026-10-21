"""Operation library tests using synthetic formats, never independent answers."""

import importlib.util
from pathlib import Path
import pytest

np = pytest.importorskip("numpy")
nib = pytest.importorskip("nibabel")
spec = importlib.util.spec_from_file_location(
    "ops_under_test", Path(__file__).parents[1] / "backend/primatex_ops.py"
)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


def test_formats_and_explicit_unassigned(tmp_path):
    path = tmp_path / "lh.thickness"
    nib.freesurfer.write_morph_data(str(path), np.array([0, 2, 4, 6], dtype=np.float32))
    assert ops.read_surface_metric(path).tolist() == [0, 2, 4, 6]
    ann = tmp_path / "lh.aparc.annot"
    table = np.array([[0, 0, 0, 0], [20, 30, 40, 0], [50, 60, 70, 0]])
    nib.freesurfer.write_annot(
        str(ann), np.array([-1, 1, 1, 2]), table, [b"unknown", b"one", b"two"]
    )
    labels, names, ctab = ops.read_annotation(ann)
    assert labels.tolist() == [-1, 1, 1, 2] and names == ["unknown", "one", "two"]
    assert ctab.shape == (3, 5)
    lab = tmp_path / "lh.cortex.label"
    lab.write_text("#!ascii label\n3\n0 0 0 0 0\n1 0 0 0 0\n2 0 0 0 0\n")
    mask = ops.read_label(lab)
    rows = ops.parcel_summary(
        ops.read_surface_metric(path),
        labels,
        [{"key": 1, "name": "one"}, {"key": 2, "name": "two"}],
        mask=mask,
    )
    assert (
        rows[0]["vertex_count"] == 2
        and rows[0]["mean"] == 3
        and rows[0]["std_population"] == 1
    )
    assert rows[1]["vertex_count"] == 0 and rows[1]["mean"] is None


def test_weighted_and_zero_values():
    row = ops.parcel_summary([0, 2, 4], np.array([1, 1, 1]), [1], weights=[1, 2, 1])[0]
    assert row["mean"] == 2 and row["std_population"] == pytest.approx(2**0.5)
    assert row["median"] == 2 and row["zero_count"] == 1 and row["vertex_count"] == 3
    assert ops.parcel_summary([0], np.array([1]), [1], weights=[0])[0]["mean"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mask": [4]},
        {"mask": np.array([True])},
        {"mask": [1, 1]},
        {"weights": [1, -1, 1]},
        {"weights": [1, float("nan"), 1]},
        {"label_set": [1, 1]},
    ],
)
def test_invalid_masks_weights_or_labels_fail(kwargs):
    args = {
        "metric": [1, 2, 3],
        "vertex_labels": np.array([1, 1, 2]),
        "label_set": [1, 2],
        **kwargs,
    }
    with pytest.raises(ValueError):
        ops.parcel_summary(**args)


def test_nonfinite_and_cardinality_fail():
    with pytest.raises(ValueError):
        ops.parcel_summary([1, float("nan")], np.array([1, 1]), [1])
    with pytest.raises(ValueError):
        ops.parcel_summary([1, 2], np.array([1]), [1])


def test_mesh_area_and_hull(tmp_path):
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    faces = np.array([[0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]], dtype=np.int32)
    path = tmp_path / "lh.pial"
    nib.freesurfer.write_geometry(str(path), vertices, faces)
    v, f = ops.read_surface(path)
    assert np.array_equal(v, vertices) and np.array_equal(f, faces)
    expected = 1.5 + np.sqrt(3) / 2
    assert ops.vertex_area(v, f).sum() == pytest.approx(expected)
    pytest.importorskip("scipy")
    result = ops.convex_hull_area_ratio(v, f)
    assert result["surface_area"] == pytest.approx(expected) and result[
        "area_ratio"
    ] == pytest.approx(1)
    assert result["is_local_gyrification_index"] is False


def test_gifti_shape_and_label(tmp_path):
    path = tmp_path / "test.shape.gii"
    nib.save(
        nib.gifti.GiftiImage(
            darrays=[
                nib.gifti.GiftiDataArray(
                    np.array([1, 2, 3], dtype=np.float32), intent="NIFTI_INTENT_SHAPE"
                )
            ]
        ),
        str(path),
    )
    assert ops.read_surface_metric(path).tolist() == [1, 2, 3]
    image = nib.gifti.GiftiImage(
        darrays=[
            nib.gifti.GiftiDataArray(
                np.array([0, 3, 3], dtype=np.int32), intent="NIFTI_INTENT_LABEL"
            )
        ]
    )
    path = tmp_path / "test.label.gii"
    nib.save(image, str(path))
    assert ops.read_label_gifti(path)[0].tolist() == [0, 3, 3]


def test_dynamic_stats_columns_and_units(tmp_path):
    path = tmp_path / "x.stats"
    path.write_text("# ColHeaders ThickAvg StructName NumVert\n2.5 region 10\n")
    assert ops.read_stats_table(path)["rows"] == [
        {"ThickAvg": "2.5", "StructName": "region", "NumVert": "10"}
    ]
    path.write_text(
        "# TableCol 1 ColHeader StructName\n# TableCol 2 ColHeader ThickAvg\nregion 3.1\n"
    )
    assert ops.read_stats_table(path)["rows"][0]["ThickAvg"] == "3.1"
    path.write_text("# ColHeaders A B\n1\n")
    with pytest.raises(ValueError):
        ops.read_stats_table(path)


def test_header_units_not_inferred(tmp_path):
    path = tmp_path / "t.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((2, 3, 4)), np.diag([2, 3, 4, 1])), str(path))
    info = ops.nifti_info(path)
    assert info["shape"] == [2, 3, 4] and info["voxel_size"] == [2, 3, 4]
    assert (
        info["voxel_size_units"] == "unknown"
        and info["physical_scale_verified"] is False
    )
